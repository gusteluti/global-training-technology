import json
import os
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Dict, List, Tuple
from agents.course_agent import CourseAgent
from agents.groq_client import GroqChatClient
from agents.llm_guard import (
    POLICY_BLOCK,
    InputBlockedError,
    LLMUnavailableError,
    entrada_bloqueada,
    filtrar_saida,
    precos_do_catalogo,
)

# Load environment variables if not already loaded
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_SESSION_ID = re.compile(r"[0-9a-f]{32}")


class ManagerAgent:
    """
    Manager agent that identifies user intent and routes to appropriate course agents
    Uses Groq LLM for fast inference
    """
    
    def __init__(self):
        self.courses: Dict = {}
        self.course_agents: Dict[str, CourseAgent] = {}
        self.sessions: Dict = {}  # Store conversation history per session
        self.courses_fingerprint: Dict[str, Tuple[int, int]] = {}

        # Fase 2 - Observabilidade do Chatbot (RF24): contadores simples em
        # memória usados pelo Dashboard de Observabilidade de IA.
        self.metrics = {
            "total_messages": 0,
            "course_specific_messages": 0,
            "unresolved_messages": 0,  # perguntas gerais que não bateram com nenhum curso
            "messages_per_course": {},
        }

        # Initialize Groq chat client
        self.llm = GroqChatClient()
        self.courses_dir = Path(__file__).parent.parent / "courses"
        print(f"[OK] ManagerAgent using Groq model: {self.llm.model}")

    def get_observability_snapshot(self) -> Dict:
        """Métricas de uso do chatbot para o painel administrativo (RF24)."""
        return {
            "total_sessions": len(self.sessions),
            "total_messages": self.metrics["total_messages"],
            "course_specific_messages": self.metrics["course_specific_messages"],
            "unresolved_messages": self.metrics["unresolved_messages"],
            "messages_per_course": dict(self.metrics["messages_per_course"]),
            "model": self.llm.model,
        }
        
    def load_courses(self, reload: bool = False):
        """Load all courses from JSON files in courses directory"""
        if not self.courses_dir.exists():
            print(f"[AVISO]  Courses directory not found: {self.courses_dir}")
            self.courses = {}
            self.course_agents = {}
            self.courses_fingerprint = {}
            return 0

        courses: Dict = {}
        course_agents: Dict[str, CourseAgent] = {}
        fingerprint = self._get_courses_fingerprint()
            
        for course_file in self.courses_dir.glob("*.json"):
            try:
                with open(course_file, 'r', encoding='utf-8') as f:
                    course_data = json.load(f)
                    course_id = course_data.get('id', course_file.stem)
                    courses[course_id] = course_data
                    
                    # Create course agent for this course
                    course_agents[course_id] = CourseAgent(course_data)
                    print(f"[OK] Loaded course: {course_data.get('name')}")
            except Exception as e:
                print(f"[FALHA] Error loading {course_file}: {str(e)}")

        self.courses = courses
        self.course_agents = course_agents
        self.courses_fingerprint = fingerprint
        return len(self.courses)

    def refresh_courses_if_changed(self) -> bool:
        """Reload course agents if JSON files changed since the last load."""
        current_fingerprint = self._get_courses_fingerprint()
        if current_fingerprint != self.courses_fingerprint:
            previous_count = len(self.courses)
            loaded_count = self.load_courses(reload=True)
            print(
                "[RECARREGA] Course files changed. "
                f"ManagerAgent refreshed from {previous_count} to {loaded_count} course(s)."
            )
            return True
        return False

    def _get_courses_fingerprint(self) -> Dict[str, Tuple[int, int]]:
        """Return a lightweight signature for all course JSON files."""
        if not self.courses_dir.exists():
            return {}

        fingerprint = {}
        for course_file in self.courses_dir.glob("*.json"):
            try:
                stat = course_file.stat()
                fingerprint[str(course_file)] = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                continue
        return fingerprint
    
    def get_course_names_list(self) -> str:
        """Return formatted list of available courses"""
        if not self.courses:
            return "Nenhum curso disponível no momento."
        
        courses_list = []
        for course in self.courses.values():
            name = course.get('name', 'Unknown')
            price = course.get('price', 'N/A')
            courses_list.append(f"• {name} (R$ {price})")
        
        return "\n".join(courses_list)
    
    def create_system_prompt(self) -> str:
        """Create the system prompt for the manager agent"""
        courses_info = self.get_course_names_list()
        
        return f"""{POLICY_BLOCK}
Você é um assistente gerenciador de cursos de uma escola de tecnologia.

CURSOS DISPONÍVEIS:
{courses_info}

Sua função é:
1. Entender o que o usuário quer (qual curso, informações gerais, preço, etc)
2. Fornecer informações persuasivas sobre os cursos
3. Ajudar na decisão de compra
4. Rotear para agentes especializados quando necessário

INSTRUÇÕES IMPORTANTES:
- Seja amigável e profissional
- Se não conseguir entender, peça clarificação
- Incentive o usuário a conhecer os cursos
- Esteja sempre pronto para discutir preços, duração, objetivos
- Se o usuário pedir detalhes muito específicos de um curso, mencione que pode ajudar melhor

Responda em português (pt-BR)."""
    
    def identify_course_intent(self, user_message: str) -> Tuple[str, bool]:
        """
        Identify which course (if any) the user is interested in
        Returns: (course_id, is_course_specific)
        """
        # Simple keyword matching first (fast)
        message_lower = self._normalize_text(user_message)
        
        for course_id, course_data in self.courses.items():
            course_name = self._normalize_text(course_data.get('name', ''))
            normalized_course_id = self._normalize_text(course_id.replace("_", " "))
            if course_name and course_name in message_lower:
                return course_id, True
            if normalized_course_id and normalized_course_id in message_lower:
                return course_id, True
            if self._matches_course_keywords(message_lower, course_name, normalized_course_id):
                return course_id, True
        
        # If no direct match, use LLM to identify
        try:
            identify_prompt = f"""Dado o seguinte texto do usuário, identifique se ele está perguntando sobre um curso específico.

CURSOS DISPONÍVEIS:
{self._get_courses_for_routing()}

MENSAGEM DO USUÁRIO: {user_message}

Responda com apenas o ID do curso ou "GENERAL" se for pergunta geral.
"""
            response_text = self.llm.create_chat_completion([
                {"role": "system", "content": "Você é um assistente que identifica intenções. Responda com apenas uma palavra."},
                {"role": "user", "content": identify_prompt}
            ], max_tokens=200, temperature=0.3)
            result = response_text.strip().strip('`"\'').split()[0]
            course_lookup = {course_id.lower(): course_id for course_id in self.courses}
            
            if result.lower() in course_lookup:
                return course_lookup[result.lower()], True
                
        except Exception as e:
            print(f"Error in course identification: {type(e).__name__}")
        
        return "GENERAL", False

    def _normalize_text(self, value: str) -> str:
        """Normalize text for accent-insensitive and case-insensitive matching."""
        normalized = unicodedata.normalize("NFD", value or "")
        without_accents = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
        return " ".join(without_accents.lower().replace("_", " ").split())

    def _matches_course_keywords(self, message: str, course_name: str, course_id: str) -> bool:
        """Match important course words so "tem Python?" finds "Python Básico"."""
        ignored_terms = {
            "curso", "basico", "avancado", "intermediario", "profissional",
            "online", "ead", "presencial", "in", "company", "de", "do", "da",
        }
        short_technical_terms = {
            "c", "c#", "c++", "js", "ts", "bi", "ui", "ux", "sql", "vba", "ia", "ai",
        }
        terms = set(course_name.split()) | set(course_id.split())
        relevant_terms = [
            term
            for term in terms
            if term not in ignored_terms
            and (len(term) >= 3 or term in short_technical_terms or any(char in term for char in "#+"))
        ]
        return any(self._contains_term(message, term) for term in relevant_terms)

    def _contains_term(self, message: str, term: str) -> bool:
        if not term:
            return False
        if any(char in term for char in "#+"):
            return term in message
        return re.search(rf"(^|\s){re.escape(term)}($|\s)", message) is not None
    
    def _get_courses_for_routing(self) -> str:
        """Get courses list for routing prompt"""
        courses_list = []
        for course_id, course_data in self.courses.items():
            name = course_data.get('name', 'Unknown')
            courses_list.append(f"{course_id}: {name}")
        return "\n".join(courses_list)
    
    def resolve_session(self, session_id: str = None) -> str:
        """Id de sessão anônima efetivo (E6, D38.1).

        Só continua a sessão se o id foi emitido por este servidor (uuid4 em hex) e ela ainda existe
        em `self.sessions`. Qualquer outro valor (ausente, 'default', 'web-chat-session', inventado,
        truncado, sessão extinta) abre uma sessão nova com id novo; o valor do cliente nunca é ecoado.
        """
        if isinstance(session_id, str) and _SESSION_ID.fullmatch(session_id) and session_id in self.sessions:
            return session_id
        novo = uuid.uuid4().hex
        while novo in self.sessions:
            novo = uuid.uuid4().hex
        self.sessions[novo] = []
        return novo

    def _filtrar_saida(self, resposta: str) -> str:
        """Filtro de saída (D38.5): descarta desconto, valor fora do catálogo e vazamento de prompt."""
        return filtrar_saida(resposta, precos_do_catalogo(self.courses.values()))

    def process_message(self, user_message: str, session_id: str) -> str:
        """
        Process user message and route to appropriate agent or respond directly.

        `session_id` deve vir de `resolve_session`. Levanta InputBlockedError (injeção direta; nada é
        gravado e o LLM não é chamado) ou LLMUnavailableError (falha do provedor; nada é gravado).
        """
        if entrada_bloqueada(user_message):
            raise InputBlockedError()

        self.refresh_courses_if_changed()

        # Initialize session if not exists
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        
        # Identify course intent
        course_id, is_specific = self.identify_course_intent(user_message)

        self._register_metrics(course_id, is_specific)

        # Get conversation history for context
        conversation_history = self.sessions[session_id].copy()
        conversation_history.append({"role": "user", "content": user_message})
        
        # If course-specific, use course agent
        if is_specific and course_id in self.course_agents:
            response = self.course_agents[course_id].answer_question(
                user_message, 
                conversation_history
            )
        else:
            # Use manager agent for general questions
            response = self._answer_general_question(user_message, conversation_history)

        response = self._filtrar_saida(response)
        
        # Store in history
        self.sessions[session_id].append({"role": "user", "content": user_message})
        self.sessions[session_id].append({"role": "assistant", "content": response})
        
        # Keep only last 20 messages in history to avoid context overflow
        if len(self.sessions[session_id]) > 40:
            self.sessions[session_id] = self.sessions[session_id][-40:]
        
        return response
    
    def _register_metrics(self, course_id: str, is_specific: bool):
        """Fase 2 - Observabilidade: contabiliza volume de requisições e
        tópicos não compreendidos pelo modelo (RF24)."""
        self.metrics["total_messages"] += 1
        if is_specific:
            self.metrics["course_specific_messages"] += 1
            self.metrics["messages_per_course"][course_id] = (
                self.metrics["messages_per_course"].get(course_id, 0) + 1
            )
        else:
            self.metrics["unresolved_messages"] += 1

    def process_authenticated_message(self, user_message: str, student_context: str, history: List) -> str:
        """Chat do aluno logado (E5). Não lê nem grava em self.sessions.

        `history` são as mensagens persistidas do próprio aluno (anteriores à atual, já limitadas pelo
        chamador) e `student_context` é o texto com nome e cursos ativos. Os dois chegam ao LLM tanto
        na resposta geral quanto no Course Agent. A persistência fica com o chamador.

        Levanta InputBlockedError (nada deve ser gravado) ou LLMUnavailableError (nada deve ser gravado).
        Saída barrada pelo filtro volta como texto fixo, que o chamador grava no lugar do texto cru.
        """
        if entrada_bloqueada(user_message):
            raise InputBlockedError()

        self.refresh_courses_if_changed()

        course_id, is_specific = self.identify_course_intent(user_message)
        self._register_metrics(course_id, is_specific)

        conversation_history = [{"role": m["role"], "content": m["content"]} for m in history]
        conversation_history.append({"role": "user", "content": user_message})
        limit = len(conversation_history)

        if is_specific and course_id in self.course_agents:
            resposta = self.course_agents[course_id].answer_question(
                user_message, conversation_history, student_context=student_context, history_limit=limit
            )
        else:
            resposta = self._answer_general_question(
                user_message, conversation_history, student_context=student_context, history_limit=limit
            )
        return self._filtrar_saida(resposta)

    def _answer_general_question(
        self, user_message: str, history: List, student_context: str = None, history_limit: int = 10
    ) -> str:
        """Answer a general question using the LLM"""
        try:
            # Build messages for LLM
            messages = [{"role": "system", "content": self.create_system_prompt()}]
            if student_context:
                messages.append({"role": "system", "content": student_context})

            # Add conversation history (last entries only, to avoid overflow)
            for msg in history[-history_limit:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Get response from Groq
            response_text = self.llm.create_chat_completion(messages, max_tokens=600)
            return response_text
            
        except Exception as e:
            # Só o tipo da exceção vai ao log; o texto pode conter detalhes do provedor (E6, D38.6).
            print(f"Error in general question: {type(e).__name__}")
            raise LLMUnavailableError() from None

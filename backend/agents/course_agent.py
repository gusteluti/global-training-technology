import os
from typing import Dict, List
from agents.groq_client import GroqChatClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class CourseAgent:
    """
    Template for course-specific agents
    Each course gets its own instance with specific knowledge
    Uses Groq LLM for fast responses
    """
    
    def __init__(self, course_data: Dict):
        self.course_data = course_data
        self.course_id = course_data.get('id')
        self.course_name = course_data.get('name')
        
        # Initialize Groq chat client
        self.llm = GroqChatClient()
        
    def build_knowledge_base(self) -> str:
        """Build the knowledge base string from course data"""
        course = self.course_data
        
        knowledge = f"""
╔════════════════════════════════════════════════════════════════╗
║ CURSO: {course.get('name')}
╚════════════════════════════════════════════════════════════════╝

📝 DESCRIÇÃO:
{course.get('description')}

💰 PREÇO: R$ {course.get('price')}
⏱️  DURAÇÃO: {course.get('duration_hours')} horas
📊 NÍVEL: {course.get('level')}
👥 PÚBLICO-ALVO: {course.get('target_audience')}

🎯 OBJETIVOS:
{self._format_list(course.get('objectives', []))}

📚 TÓPICOS ABORDADOS:
{self._format_list(course.get('topics', []))}

✨ BENEFÍCIOS:
{self._format_list(course.get('benefits', []))}

❓ PERGUNTAS FREQUENTES:
{self._format_faq(course.get('faq', []))}
"""
        return knowledge
    
    def _format_list(self, items: List[str]) -> str:
        """Format a list of items with bullet points"""
        if not items:
            return "Sem informações disponíveis"
        return "\n".join([f"  • {item}" for item in items])
    
    def _format_faq(self, faq_list: List[Dict]) -> str:
        """Format FAQ items"""
        if not faq_list:
            return "Sem perguntas frequentes cadastradas"
        
        formatted = ""
        for i, item in enumerate(faq_list, 1):
            formatted += f"\n  {i}. P: {item.get('question')}\n"
            formatted += f"     R: {item.get('answer')}\n"
        return formatted
    
    def get_system_prompt(self) -> str:
        """Get the system prompt for this course agent"""
        knowledge = self.build_knowledge_base()
        system_prompt = self.course_data.get('system_prompt', '')
        
        return f"""{system_prompt}

═══════════════════════════════════════════════════════════════════
BASE DE CONHECIMENTO DO CURSO
═══════════════════════════════════════════════════════════════════

{knowledge}

═══════════════════════════════════════════════════════════════════
INSTRUÇÕES OPERACIONAIS
═══════════════════════════════════════════════════════════════════

✅ FAÇA:
• Responda todas as perguntas baseado APENAS na base de conhecimento acima
• Seja amigável, didático e motivador
• Destaque os benefícios do curso
• Se perguntarem sobre inscrição/compra, seja persuasivo
• Use emojis para deixar a resposta mais atrativa

❌ NÃO FAÇA:
• Não invente informações não presentes na base de conhecimento
• Se perguntarem algo fora do escopo do curso, redirecione gentilmente
• Não responda sobre outros cursos (você só conhece este)

🎯 OBJETIVO FINAL:
Ajude o usuário a entender o valor do curso e incentive a inscrição!

Responda em português (pt-BR)."""
    
    def answer_question(
        self,
        question: str,
        conversation_history: List = None,
        student_context: str = None,
        history_limit: int = 10,
    ) -> str:
        """
        Answer a question about the course
        
        Args:
            question: User's question
            conversation_history: Previous messages for context
            student_context: Optional text about the logged-in student (E5), sent as an extra system message
            history_limit: How many entries of the history are sent to the model

        Returns:
            Course agent's response
        """
        try:
            if conversation_history is None:
                conversation_history = []
            
            # Build messages for Groq chat
            messages = [{"role": "system", "content": self.get_system_prompt()}]
            if student_context:
                messages.append({"role": "system", "content": student_context})

            # Add conversation history (last entries only, to avoid overflow)
            for msg in conversation_history[-history_limit:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Get response from Groq
            response_text = self.llm.create_chat_completion(messages, max_tokens=800)
            return response_text
            
        except Exception as e:
            error_msg = f"Desculpe, ocorreu um erro ao processar sua pergunta sobre {self.course_name}: {str(e)}"
            print(f"Error in course agent ({self.course_id}): {error_msg}")
            return error_msg

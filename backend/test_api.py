#!/usr/bin/env python3
"""
Simple test script to test the chatbot API with Groq LLM
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_health():
    """Test health check endpoint"""
    print("\n🏥 Testing /health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        data = response.json()
        print(json.dumps(data, indent=2))
        if response.status_code == 200:
            print("✅ Health check passed!")
            return True
        else:
            print(f"❌ Health check failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_chat(message, session_id="test_session"):
    """Test chat endpoint"""
    print(f"\n💬 Sending chat message: '{message}'")
    print(f"   Session ID: {session_id}")
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": message, "session_id": session_id},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        if response.status_code == 200:
            print(f"\n📝 Response:")
            print(data.get("message", "No message"))
            print("\n✅ Chat test passed!")
            return True
        else:
            print(f"❌ Chat failed with status {response.status_code}")
            print(json.dumps(data, indent=2))
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_list_courses():
    """Test listing courses"""
    print("\n📚 Testing /api/admin/courses endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/api/admin/courses")
        data = response.json()
        
        if response.status_code == 200:
            print(f"✅ Found {data.get('total', 0)} courses:")
            if data.get('courses'):
                for course in data['courses']:
                    print(f"  • {course.get('name')} (R$ {course.get('price')})")
            print("✅ Course listing passed!")
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def interactive_chat(session_id="interactive_session"):
    """Run interactive chat"""
    print("\n\n🤖 === INTERACTIVE CHAT MODE ===")
    print("Type 'exit' to quit, 'new' for new session\n")
    
    while True:
        try:
            message = input("You: ").strip()
            
            if message.lower() == "exit":
                print("Goodbye!")
                break
            elif message.lower() == "new":
                session_id = f"session_{len(session_id)}"
                print(f"New session: {session_id}\n")
                continue
            elif not message:
                continue
            
            # Send message
            response = requests.post(
                f"{BASE_URL}/api/chat",
                json={"message": message, "session_id": session_id},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    print(f"\n🤖 Bot: {data.get('message')}\n")
                else:
                    print(f"\n❌ Error: {data.get('message')}\n")
            else:
                print(f"\n❌ Request failed: {response.status_code}\n")
                
        except requests.Timeout:
            print("⏱️  Request timed out. The LLM might be processing. Try again.")
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}\n")

def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 TCC School Chatbot - API Test Suite")
    print("=" * 60)
    
    # Check if server is running
    try:
        requests.get(f"{BASE_URL}/health", timeout=2)
    except:
        print("❌ Server is not running!")
        print(f"   Make sure to run 'python app.py' in the backend/ directory")
        sys.exit(1)
    
    # Run tests
    print("\n1️⃣ Running pre-flight tests...")
    
    if not test_health():
        print("❌ Server health check failed. Exiting.")
        sys.exit(1)
    
    if not test_list_courses():
        print("⚠️  Could not list courses (this is ok if none exist yet)")
    
    print("\n2️⃣ Testing chat with Groq LLM...")
    
    # Test general question
    if test_chat("Olá! Quais cursos vocês têm?"):
        print("✅ General question test passed!")
    else:
        print("❌ General question test failed!")
    
    print("\n" + "=" * 60)
    print("✅ All pre-flight tests completed!")
    print("=" * 60)
    
    # Ask if user wants interactive mode
    try:
        response = input("\nWould you like to test interactive chat? (y/n): ").strip().lower()
        if response == "y":
            interactive_chat()
    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == "__main__":
    main()

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict
import json
from pathlib import Path

router = APIRouter()
COURSES_DIR = Path(__file__).parent.parent / "courses"

class CourseInput(BaseModel):
    """Schema for creating/updating a course"""
    id: str
    name: str
    description: str
    price: float
    duration_hours: int
    level: str
    target_audience: str
    objectives: List[str]
    topics: List[str]
    benefits: List[str]
    faq: List[Dict[str, str]]
    system_prompt: str

@router.post("/create-course")
async def create_course(course: CourseInput, request: Request):
    """
    Create a new course from form data
    Saves as JSON file in courses directory
    """
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        courses_dir.mkdir(exist_ok=True)
        
        # Create course file
        course_file = courses_dir / f"{course.id}.json"
        
        # Check if course already exists
        if course_file.exists():
            raise HTTPException(status_code=400, detail="Course with this ID already exists")
        
        # Prepare course data
        course_data = {
            **course.dict(),
            "created_at": __import__('datetime').datetime.now().isoformat()
        }
        
        # Save to JSON
        with open(course_file, 'w', encoding='utf-8') as f:
            json.dump(course_data, f, ensure_ascii=False, indent=2)
        
        reload_manager_agent_courses(request, f"course creation: {course.id}")
        
        return {
            "status": "success",
            "message": f"Course '{course.name}' created successfully",
            "course_id": course.id,
            "file": str(course_file)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating course: {str(e)}")

@router.get("/courses")
async def list_courses():
    """List all available courses"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        courses = []
        
        if courses_dir.exists():
            for course_file in courses_dir.glob("*.json"):
                with open(course_file, 'r', encoding='utf-8') as f:
                    course_data = json.load(f)
                    courses.append({
                        "id": course_data.get('id'),
                        "name": course_data.get('name'),
                        "price": course_data.get('price'),
                        "level": course_data.get('level')
                    })
        
        return {
            "status": "success",
            "total": len(courses),
            "courses": courses
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing courses: {str(e)}")

@router.get("/course/{course_id}")
async def get_course(course_id: str):
    """Get full details of a specific course"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        course_file = courses_dir / f"{course_id}.json"
        
        if not course_file.exists():
            raise HTTPException(status_code=404, detail="Course not found")
        
        with open(course_file, 'r', encoding='utf-8') as f:
            course_data = json.load(f)
        
        return {
            "status": "success",
            "course": course_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving course: {str(e)}")

@router.put("/course/{course_id}")
async def update_course(course_id: str, course: CourseInput, request: Request):
    """Update an existing course"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        course_file = courses_dir / f"{course_id}.json"
        
        if not course_file.exists():
            raise HTTPException(status_code=404, detail="Course not found")
        
        # Load existing data to preserve creation date
        with open(course_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        
        # Update with new data
        course_data = {
            **course.dict(),
            "created_at": existing_data.get('created_at'),
            "updated_at": __import__('datetime').datetime.now().isoformat()
        }
        
        # Save updated course
        with open(course_file, 'w', encoding='utf-8') as f:
            json.dump(course_data, f, ensure_ascii=False, indent=2)

        reload_manager_agent_courses(request, f"course update: {course_id}")
        
        return {
            "status": "success",
            "message": f"Course '{course.name}' updated successfully",
            "course_id": course_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating course: {str(e)}")

@router.delete("/course/{course_id}")
async def delete_course(course_id: str, request: Request):
    """Delete a course"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        course_file = courses_dir / f"{course_id}.json"
        
        if not course_file.exists():
            raise HTTPException(status_code=404, detail="Course not found")
        
        # Load course name before deleting
        with open(course_file, 'r', encoding='utf-8') as f:
            course_data = json.load(f)
            course_name = course_data.get('name')
        
        # Delete file
        course_file.unlink()

        reload_manager_agent_courses(request, f"course deletion: {course_id}")
        
        return {
            "status": "success",
            "message": f"Course '{course_name}' deleted successfully",
            "course_id": course_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting course: {str(e)}")

def reload_manager_agent_courses(request: Request, reason: str):
    """Reload in-memory course agents so chat can see admin changes immediately."""
    manager_agent = getattr(request.app.state, "manager_agent", None)
    if not manager_agent:
        print(f"⚠️ Manager agent not available to reload after {reason}")
        return

    manager_agent.load_courses(reload=True)
    print(f"🔄 Manager agent reloaded after {reason}")

def load_course_data(course_id: str) -> Dict:
    course_file = COURSES_DIR / f"{course_id}.json"
    if course_file.exists():
        with open(course_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    if COURSES_DIR.exists():
        for candidate in COURSES_DIR.glob("*.json"):
            with open(candidate, 'r', encoding='utf-8') as f:
                course_data = json.load(f)
            if course_data.get("id") == course_id:
                return course_data

    raise HTTPException(status_code=404, detail="Course not found")

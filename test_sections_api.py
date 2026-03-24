#!/usr/bin/env python3
"""
Test script for Section-based Assignment API
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/assignments"

def test_assignment_creation():
    """Test creating a basic assignment (without sections)"""
    print("🏗️ Creating Assignment...")
    
    with open('sample_assignment_basic.json', 'r') as f:
        assignment_data = json.load(f)
    
    try:
        response = requests.post(f"{BASE_URL}/", json=assignment_data)
        
        if response.status_code in [200, 201]:
            result = response.json()
            print("✅ Assignment created successfully!")
            print(f"📝 Assignment ID: {result['assignment_id']}")
            print(f"📊 Initial Points: {result['total_points']}")
            print(f"⏱️ Initial Time: {result['total_time_minutes']} minutes")
            print(f"📋 Section Count: {result['section_count']}")
            return result['assignment_id']
        else:
            print(f"❌ Failed! Status: {response.status_code} - {response.json()}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_section_creation(assignment_id, section_file, section_name):
    """Test creating a section within an assignment"""
    if not assignment_id:
        return None
        
    print(f"📝 Creating Section: {section_name}...")
    
    with open(section_file, 'r') as f:
        section_data = json.load(f)
    
    # Don't add assignment_id to data - it's passed in URL
    try:
        response = requests.post(f"{BASE_URL}/{assignment_id}/sections", json=section_data)
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"✅ Section '{section_name}' created successfully!")
            print(f"🆔 Section ID: {result['section_id']}")
            print(f"📊 Section Points: {result['total_points']}")
            print(f"❓ Questions: {result['question_count']}")
            return result['section_id']
        else:
            print(f"❌ Failed! Status: {response.status_code} - {response.json()}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_sections_list(assignment_id):
    """Test listing all sections for an assignment"""
    if not assignment_id:
        return
        
    print(f"📋 Listing Sections for Assignment {assignment_id}...")
    
    try:
        response = requests.get(f"{BASE_URL}/{assignment_id}/sections")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Sections retrieved successfully!")
            print(f"📊 Total Sections: {result['total_sections']}")
            print(f"🎯 Total Points: {result['total_points']}")
            print(f"⏱️ Total Time: {result['total_time_minutes']} minutes")
            
            print("\n📚 Section Details:")
            for section in result['sections']:
                print(f"  {section['order']}. {section['title']}")
                print(f"     Points: {section['total_points']}, Time: {section.get('time_limit_minutes', 'No limit')} min")
                print(f"     Questions: {len(section['questions'])}")
        else:
            print(f"❌ Failed! Status: {response.status_code} - {response.json()}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_assignment_details(assignment_id):
    """Test getting assignment details with sections"""
    if not assignment_id:
        return
        
    print(f"🔍 Getting Assignment Details for {assignment_id}...")
    
    try:
        response = requests.get(f"{BASE_URL}/{assignment_id}")
        
        if response.status_code == 200:
            assignment = response.json()
            print("✅ Assignment details retrieved!")
            print(f"📝 Title: {assignment['title']}")
            print(f"📚 Course: {assignment.get('course_name', 'No course')}")
            print(f"📊 Total Points: {assignment['total_points']}")
            print(f"⏱️ Total Time: {assignment['total_time_minutes']} minutes")
            print(f"📋 Sections: {len(assignment['sections'])}")
            
            total_questions = sum(len(section['questions']) for section in assignment['sections'])
            print(f"❓ Total Questions: {total_questions}")
            
            print("\n📚 Sections Summary:")
            for i, section in enumerate(assignment['sections'], 1):
                print(f"  {i}. {section['title']} - {section['total_points']} pts, {len(section['questions'])} questions")
                
        else:
            print(f"❌ Failed! Status: {response.status_code} - {response.json()}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_section_update(assignment_id, section_id):
    """Test updating a section"""
    if not assignment_id or not section_id:
        return
        
    print(f"✏️ Testing Section Update for {section_id}...")
    
    update_data = {
        "description": "Updated section description with new content and examples.",
        "time_limit_minutes": 40
    }
    
    try:
        response = requests.put(f"{BASE_URL}/{assignment_id}/sections/{section_id}", json=update_data)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Section updated successfully!")
            print(f"Status: {result['status']}")
        else:
            print(f"❌ Failed! Status: {response.status_code} - {response.json()}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_section_details(assignment_id, section_id, section_name):
    """Test getting individual section details"""
    if not assignment_id or not section_id:
        return
        
    print(f"🔍 Getting Section Details: {section_name}...")
    
    try:
        response = requests.get(f"{BASE_URL}/{assignment_id}/sections/{section_id}")
        
        if response.status_code == 200:
            section = response.json()
            print(f"✅ Section '{section_name}' details:")
            print(f"📝 Title: {section['title']}")
            print(f"📊 Points: {section['total_points']}")
            print(f"⏱️ Time Limit: {section.get('time_limit_minutes', 'No limit')} minutes")
            print(f"📋 Order: {section['order']}")
            print(f"❓ Questions: {len(section['questions'])}")
            
            question_types = {}
            for q in section['questions']:
                q_type = q['question_type']
                question_types[q_type] = question_types.get(q_type, 0) + 1
                
            print("Question breakdown:", dict(question_types))
        else:
            print(f"❌ Failed! Status: {response.status_code} - {response.json()}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    print("🚀 Section-Based Assignment Test Suite")
    print("=" * 60)
    
    # Step 1: Create Assignment
    assignment_id = test_assignment_creation()
    if not assignment_id:
        print("❌ Cannot continue without assignment_id")
        return
    
    print("\n" + "="*60 + "\n")
    
    # Step 2: Create Sections
    sections = [
        ('sample_section1_data_structures.json', 'Data Structures'),
        ('sample_section2_algorithms.json', 'Algorithms'),
        ('sample_section3_oop.json', 'OOP')
    ]
    
    section_ids = []
    for section_file, section_name in sections:
        section_id = test_section_creation(assignment_id, section_file, section_name)
        section_ids.append(section_id)
        print()
    
    print("\n" + "="*60 + "\n")
    
    # Step 3: List all sections
    test_sections_list(assignment_id)
    
    print("\n" + "="*60 + "\n")
    
    # Step 4: Get complete assignment details
    test_assignment_details(assignment_id)
    
    print("\n" + "="*60 + "\n")
    
    # Step 5: Test individual section details
    for i, (section_id, (_, section_name)) in enumerate(zip(section_ids, sections)):
        if section_id:
            test_section_details(assignment_id, section_id, section_name)
            print()
    
    print("="*60 + "\n")
    
    # Step 6: Test section update
    if section_ids[0]:  # Update first section
        test_section_update(assignment_id, section_ids[0])
        print()
    
    print("\n🎉 Section-Based Assignment Test Completed!")
    print(f"📋 Assignment ID: {assignment_id}")
    print(f"📝 Sections Created: {len([s for s in section_ids if s])}")
    print("=" * 60)

if __name__ == "__main__":
    main()
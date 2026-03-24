#!/usr/bin/env python3
"""
Test script for Assignment API endpoints
"""
import requests
import json
from datetime import datetime

def test_assignment_creation():
    """Test creating a comprehensive assignment"""
    print("🧪 Testing Assignment Creation...")
    
    # Load the sample assignment
    with open('sample_assignment_comprehensive.json', 'r') as f:
        assignment_data = json.load(f)
    
    # API endpoint
    url = "http://localhost:8000/api/assignments/"
    
    try:
        # Make the request
        response = requests.post(url, json=assignment_data)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            print("✅ Assignment created successfully!")
            print(f"📝 Assignment ID: {result['assignment_id']}")
            print(f"📊 Total Points: {result['total_points']}")
            print(f"⏰ Created: {result['created_at']}")
            return result['assignment_id']
        else:
            print("❌ Assignment creation failed!")
            print(f"Error: {response.json()}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure it's running on http://localhost:8000")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_assignment_listing():
    """Test listing assignments"""
    print("\n🛒 Testing Assignment Listing...")
    
    url = "http://localhost:8000/api/assignments/"
    
    try:
        response = requests.get(url)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Assignment list retrieved successfully!")
            print(f"📊 Total assignments: {result['total_count']}")
            
            for assignment in result['assignments']:
                print(f"  📝 {assignment['title']}")
                print(f"     ID: {assignment['assignment_id']}")
                print(f"     Course: {assignment.get('course_name', 'No course')}")
                print(f"     Level: {assignment.get('level', 'N/A')}")
                print(f"     Points: {assignment['total_points']}")
                print()
        else:
            print("❌ Failed to retrieve assignments!")
            print(f"Error: {response.json()}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_assignment_details(assignment_id):
    """Test getting assignment details"""
    if not assignment_id:
        return
        
    print(f"\n🔍 Testing Assignment Details for {assignment_id}...")
    
    url = f"http://localhost:8000/api/assignments/{assignment_id}"
    
    try:
        response = requests.get(url)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            assignment = response.json()
            print("✅ Assignment details retrieved successfully!")
            print(f"📝 Title: {assignment['title']}")
            print(f"📚 Course: {assignment.get('course_name', 'No course')}")
            print(f"👨‍🏫 Instructor: {assignment.get('instructor_name', 'Unknown')}")
            print(f"📊 Questions: {len(assignment['questions'])}")
            print(f"🎯 Total Points: {assignment['total_points']}")
            print(f"⏱️ Time Limit: {assignment.get('time_limit_minutes', 'No limit')} minutes")
            print(f"🔒 Locked: {assignment['is_locked']}")
            print(f"📏 Level: {assignment['level']}")
            print(f"🔄 Max Attempts: {assignment.get('max_attempts', 'Unlimited')}")
            
            print("\n📋 Questions breakdown:")
            for q in assignment['questions']:
                print(f"  • {q['title']} ({q['question_type']}) - {q['points']} pts")
                
        else:
            print("❌ Failed to retrieve assignment details!")
            print(f"Error: {response.json()}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_assignment_availability(assignment_id):
    """Test checking assignment availability"""
    if not assignment_id:
        return
        
    print(f"\n🌟 Testing Assignment Availability for {assignment_id}...")
    
    url = f"http://localhost:8000/api/assignments/{assignment_id}/availability"
    
    try:
        response = requests.get(url)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Assignment availability checked!")
            print(f"🟢 Available: {result['available']}")
            print(f"💬 Message: {result['message']}")
        else:
            print("❌ Assignment not available!")
            print(f"Error: {response.json()}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_assignment_stats(assignment_id):
    """Test getting assignment statistics"""
    if not assignment_id:
        return
        
    print(f"\n📊 Testing Assignment Stats for {assignment_id}...")
    
    url = f"http://localhost:8000/api/assignments/{assignment_id}/stats"
    
    try:
        response = requests.get(url)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            stats = response.json()
            print("✅ Assignment stats retrieved!")
            print(f"👥 Total Students: {stats['total_students']}")
            print(f"✅ Completed: {stats['completed_submissions']}")
            print(f"📈 Average Score: {stats['average_score']:.2f}")
            print(f"🏆 Highest Score: {stats['highest_score']}")
            print(f"📉 Lowest Score: {stats['lowest_score']}")
        else:
            print("❌ Failed to retrieve assignment stats!")
            print(f"Error: {response.json()}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    print("🚀 Assignment API Test Suite")
    print("=" * 50)
    
    # Test assignment creation
    assignment_id = test_assignment_creation()
    
    # Test assignment listing
    test_assignment_listing()
    
    # Test assignment details
    test_assignment_details(assignment_id)
    
    # Test assignment availability
    test_assignment_availability(assignment_id)
    
    # Test assignment stats
    test_assignment_stats(assignment_id)
    
    print("\n🎉 Test suite completed!")
    print("=" * 50)

if __name__ == "__main__":
    main()
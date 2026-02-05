"""Test Token Management System"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"
ADMIN_KEY = "your-admin-key-here"  # 从.env文件获取

headers = {
    "X-Admin-Key": ADMIN_KEY,
    "Content-Type": "application/json"
}

def test_create_user():
    """Test: Create a user first"""
    print("\n=== Test 1: Create User ===")
    response = requests.post(
        f"{BASE_URL}/api/users",
        headers=headers,
        json={"name": "Test User", "quota": 1000000}
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    return data.get("id")

def test_create_token(user_id):
    """Test: Create a token with all features"""
    print("\n=== Test 2: Create Token ===")
    response = requests.post(
        f"{BASE_URL}/api/tokens",
        headers=headers,
        json={
            "user_id": user_id,
            "name": "GPT-4 Test Token",
            "unlimited_quota": False,
            "remain_quota": 100000,
            "expired_time": int(time.time()) + 86400 * 30,  # 30 days
            "model_limits_enabled": True,
            "model_limits": "gpt-4,gpt-4-turbo,claude-3-opus",
            "ip_whitelist": "",  # Empty = allow all
            "group": "test"
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    return data.get("key")

def test_list_tokens():
    """Test: List all tokens"""
    print("\n=== Test 3: List Tokens ===")
    response = requests.get(f"{BASE_URL}/api/tokens", headers=headers)
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Found {len(data)} tokens")
    for token in data:
        print(f"  - {token['name']}: {token['key'][:20]}... (status={token['status']})")
    return data

def test_use_token(token_key):
    """Test: Use token to make a request"""
    print("\n=== Test 4: Use Token for Chat ===")
    response = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {token_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True
        },
        stream=True
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Token authentication successful!")
    else:
        print(f"❌ Error: {response.text}")

def test_model_restriction(token_key):
    """Test: Try to use a model not in the allowed list"""
    print("\n=== Test 5: Model Restriction ===")
    response = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {token_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-3.5-turbo",  # Not in allowed list
            "messages": [{"role": "user", "content": "Hello"}]
        }
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 403:
        print("✅ Model restriction working!")
        print(f"Response: {response.json()}")
    else:
        print(f"❌ Expected 403, got {response.status_code}")

def test_update_token(token_id):
    """Test: Update token"""
    print("\n=== Test 6: Update Token ===")
    response = requests.put(
        f"{BASE_URL}/api/tokens/{token_id}",
        headers=headers,
        json={
            "name": "Updated Token Name",
            "remain_quota": 200000
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

def test_token_stats():
    """Test: Check token statistics"""
    print("\n=== Test 7: Token Statistics ===")
    response = requests.get(f"{BASE_URL}/api/tokens", headers=headers)
    tokens = response.json()
    for token in tokens:
        print(f"\nToken: {token['name']}")
        print(f"  Used Quota: {token['used_quota']}")
        print(f"  Remain Quota: {token['remain_quota']}")
        print(f"  Input Tokens: {token['input_tokens']}")
        print(f"  Output Tokens: {token['output_tokens']}")
        print(f"  Total Tokens: {token['total_tokens']}")
        print(f"  Request Count: {token['request_count']}")

def test_delete_token(token_id):
    """Test: Delete token"""
    print("\n=== Test 8: Delete Token ===")
    response = requests.delete(
        f"{BASE_URL}/api/tokens/{token_id}",
        headers=headers
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

def main():
    print("=" * 60)
    print("Token Management System Test Suite")
    print("=" * 60)
    
    try:
        # Test 1: Create user
        user_id = test_create_user()
        if not user_id:
            print("❌ Failed to create user")
            return
        
        # Test 2: Create token
        token_key = test_create_token(user_id)
        if not token_key:
            print("❌ Failed to create token")
            return
        
        # Test 3: List tokens
        tokens = test_list_tokens()
        token_id = tokens[0]["id"] if tokens else None
        
        # Test 4: Use token (will fail if no channels configured)
        test_use_token(token_key)
        
        # Test 5: Model restriction
        test_model_restriction(token_key)
        
        # Test 6: Update token
        if token_id:
            test_update_token(token_id)
        
        # Test 7: Check stats
        test_token_stats()
        
        # Test 8: Delete token (optional, comment out to keep)
        # if token_id:
        #     test_delete_token(token_id)
        
        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

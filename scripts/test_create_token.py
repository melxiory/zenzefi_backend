#!/usr/bin/env python
"""Test script to create user and access token"""
import requests
import json

BASE_URL = "http://localhost:8000"

# Disable proxy for localhost
proxies = {
    "http": None,
    "https": None
}

print("=" * 60)
print("Testing Zenzefi Backend Authentication")
print("=" * 60)

# Step 1: Register user
print("\n1. Registering user...")
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": "testuser2@test.com",
            "username": "testuser2",
            "password": "password123"
        },
        proxies=proxies
    )
    if response.status_code in [200, 201]:
        print("[OK] User registered successfully")
        print(json.dumps(response.json(), indent=2))
    elif response.status_code == 400:
        print("[WARNING] User already exists, continuing...")
    else:
        print(f"[ERROR] Registration failed: {response.status_code}")
        print(response.text)
        exit(1)
except Exception as e:
    print(f"[ERROR] Error: {e}")
    exit(1)

# Step 2: Login
print("\n2. Logging in...")
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={
            "email": "testuser2@test.com",
            "password": "password123"
        },
        proxies=proxies
    )
    if response.status_code == 200:
        data = response.json()
        jwt_token = data["access_token"]
        print("[OK] Login successful")
        print(f"JWT Token: {jwt_token[:50]}...")
    else:
        print(f"[ERROR] Login failed: {response.status_code}")
        print(response.text)
        exit(1)
except Exception as e:
    print(f"[ERROR] Error: {e}")
    exit(1)

# Step 3: Purchase access token
print("\n3. Purchasing access token (24h)...")
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/tokens/purchase",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"duration_hours": 24},
        proxies=proxies
    )
    if response.status_code in [200, 201]:
        data = response.json()
        print("[DEBUG] Response:", json.dumps(data, indent=2))

        # Try both 'token' and 'access_token' keys
        access_token = data.get("token") or data.get("access_token")
        if not access_token:
            print(f"[ERROR] No token found in response. Keys: {list(data.keys())}")
            exit(1)

        print("[OK] Access token created")
        print(f"Access Token: {access_token}")
        print(f"Duration: {data.get('duration_hours')} hours")
        print(f"Expires: {data.get('expires_at', 'Not activated yet')}")

        # Save to file for easy copy
        with open("../test_token.txt", "w") as f:
            f.write(access_token)
        print("\n[OK] Token saved to test_token.txt")

    else:
        print(f"[ERROR] Token purchase failed: {response.status_code}")
        print(response.text)
        exit(1)
except Exception as e:
    print(f"[ERROR] Error: {e}")
    exit(1)

print("\n" + "=" * 60)
print("[SUCCESS] Setup complete! Use this token in Desktop Client:")
print("=" * 60)
print(f"\nBackend URL: {BASE_URL}")
print(f"Access Token: {access_token}")
print("\n" + "=" * 60)

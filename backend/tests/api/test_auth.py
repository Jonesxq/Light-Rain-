"""Test authentication endpoints - Complete JWT Auth"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    """Test user registration"""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "newpassword123"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["username"] == "newuser"
    assert "id" in data


@pytest.mark.asyncio
async def test_login(client: AsyncClient, test_user_verified):
    """Test user login"""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user_verified.email,
            "password": "testpassword"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, test_user_verified):
    """Test token refresh"""
    # First login to get refresh token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user_verified.email,
            "password": "testpassword"
        }
    )
    refresh_token = login_response.json()["refresh_token"]
    
    # Use refresh token to get new access token
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_request_password_reset(client: AsyncClient, test_user_unverified):
    """Test password reset request"""
    response = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": test_user_unverified.email}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_verify_email_request(client: AsyncClient, test_user_unverified):
    """Test email verification request"""
    response = await client.post(
        "/api/v1/auth/resend-verification",
        json={"email": test_user_unverified.email}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient, auth_headers):
    """Test get current user"""
    response = await client.get(
        "/api/v1/users/me",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert "username" in data

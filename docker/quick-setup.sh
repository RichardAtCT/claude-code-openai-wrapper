#!/bin/bash
# Quick setup script for API key authentication

echo "Claude Code OpenAI Wrapper - Quick Setup"
echo "========================================"
echo ""
echo "Since browser authentication is complex in Docker, let's use API key authentication instead."
echo ""
echo "1. Get your Anthropic API key from: https://console.anthropic.com/account/keys"
echo "2. Set the environment variable in your docker-compose.yml:"
echo "   ANTHROPIC_API_KEY=sk-ant-..."
echo "   AUTH_METHOD=api_key"
echo ""
echo "3. Restart the container:"
echo "   docker-compose down"
echo "   docker-compose up -d"
echo ""
echo "The API will be available at http://192.168.1.11:8000"
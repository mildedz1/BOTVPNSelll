#!/bin/bash

# Master Bot Installation Script
# This script will install and configure the Master Bot

set -e  # Exit on any error

echo "🚀 Master Bot Installation Script"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Python 3.8+ is installed
check_python() {
    print_status "Checking Python version..."
    
    if command -v python3 &> /dev/null; then
        python_version=$(python3 --version | cut -d' ' -f2)
        major_version=$(echo $python_version | cut -d'.' -f1)
        minor_version=$(echo $python_version | cut -d'.' -f2)
        
        if [ "$major_version" -eq 3 ] && [ "$minor_version" -ge 8 ]; then
            print_status "Python $python_version is installed ✅"
        else
            print_error "Python 3.8+ is required, but found $python_version"
            exit 1
        fi
    else
        print_error "Python 3 is not installed"
        exit 1
    fi
}

# Check if pip is installed
check_pip() {
    print_status "Checking pip..."
    
    if command -v pip3 &> /dev/null; then
        print_status "pip3 is installed ✅"
    else
        print_error "pip3 is not installed"
        print_status "Installing pip3..."
        
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y python3-pip
        elif command -v yum &> /dev/null; then
            sudo yum install -y python3-pip
        else
            print_error "Could not install pip3. Please install it manually."
            exit 1
        fi
    fi
}

# Install Python dependencies
install_dependencies() {
    print_status "Installing Python dependencies..."
    
    if [ -f "requirements.txt" ]; then
        pip3 install --user -r requirements.txt
        print_status "Dependencies installed ✅"
    else
        print_error "requirements.txt not found"
        exit 1
    fi
}

# Create .env file from example
setup_env() {
    print_status "Setting up environment configuration..."
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_warning "Created .env file from .env.example"
            print_warning "Please edit .env file with your actual values!"
        else
            print_error ".env.example file not found"
            exit 1
        fi
    else
        print_status ".env file already exists"
    fi
}

# Create systemd service file
create_service() {
    print_status "Creating systemd service..."
    
    current_dir=$(pwd)
    user=$(whoami)
    
    cat > master-bot.service << EOF
[Unit]
Description=Master Bot - VPN Bot Deployment Service
After=network.target

[Service]
Type=simple
User=$user
WorkingDirectory=$current_dir
Environment=PATH=$current_dir/venv/bin
ExecStart=/usr/bin/python3 $current_dir/start_master_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    print_status "Service file created: master-bot.service"
    print_warning "To install the service, run:"
    print_warning "  sudo cp master-bot.service /etc/systemd/system/"
    print_warning "  sudo systemctl enable master-bot"
    print_warning "  sudo systemctl start master-bot"
}

# Make scripts executable
make_executable() {
    print_status "Making scripts executable..."
    chmod +x start_master_bot.py
    chmod +x install.sh
}

# Check Docker installation
check_docker() {
    print_status "Checking Docker installation..."
    
    if command -v docker &> /dev/null; then
        print_status "Docker is installed ✅"
        
        # Check if user is in docker group
        if groups $USER | grep &>/dev/null '\bdocker\b'; then
            print_status "User is in docker group ✅"
        else
            print_warning "User is not in docker group"
            print_warning "Run: sudo usermod -aG docker $USER"
            print_warning "Then logout and login again"
        fi
    else
        print_warning "Docker is not installed"
        print_warning "Install Docker: https://docs.docker.com/engine/install/"
    fi
}

# Main installation function
main() {
    echo
    print_status "Starting Master Bot installation..."
    echo
    
    # Run checks and installations
    check_python
    check_pip
    install_dependencies
    setup_env
    make_executable
    check_docker
    create_service
    
    echo
    echo "=================================="
    print_status "Installation completed! 🎉"
    echo "=================================="
    echo
    print_warning "Next steps:"
    echo "1. Edit .env file with your bot token and settings"
    echo "2. Run: python3 start_master_bot.py"
    echo "3. Or install as service using the commands shown above"
    echo
    print_warning "Required .env variables:"
    echo "- MASTER_BOT_TOKEN: Your Telegram bot token"
    echo "- MASTER_ADMIN_ID: Your Telegram user ID"
    echo "- Payment gateway settings (AQAY, cards, crypto)"
    echo
    print_status "For more information, see README.md"
}

# Run main function
main
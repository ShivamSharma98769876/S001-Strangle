#!/usr/bin/env python3
"""
Setup script for Options Trading Bot
"""
import os
import sys
import subprocess
import shutil

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True

def install_dependencies():
    """Install required dependencies"""
    print("📦 Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def setup_environment():
    """Setup environment file"""
    env_file = ".env"
    env_example = "env_example.txt"
    
    if os.path.exists(env_file):
        print(f"✅ Environment file already exists: {env_file}")
        return True
    
    if os.path.exists(env_example):
        try:
            shutil.copy(env_example, env_file)
            print(f"✅ Created environment file: {env_file}")
            print("📝 Please edit the .env file with your Kite Connect credentials")
            return True
        except Exception as e:
            print(f"❌ Failed to create environment file: {e}")
            return False
    else:
        print("❌ env_example.txt not found")
        return False

def create_directories():
    """Create necessary directories"""
    directories = ["logs", "data"]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"✅ Created directory: {directory}")

def main():
    print("🚀 Options Trading Bot Setup")
    print("=" * 40)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        sys.exit(1)
    
    # Setup environment
    if not setup_environment():
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    print("\n🎉 Setup completed successfully!")
    print("\n📋 Next steps:")
    print("1. Edit the .env file with your Kite Connect credentials")
    print("2. Run the web interface: streamlit run app.py")
    print("3. Or run the CLI: python main.py")
    print("\n📖 For more information, see README.md")

if __name__ == "__main__":
    main()

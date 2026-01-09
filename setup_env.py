#!/usr/bin/env python3
"""
Setup script to create .env file with API credentials
"""

import os

def create_env_file():
    """
    Create .env file with API credentials from InstallLibs.py
    """
    
    # API credentials from InstallLibs.py
    api_key = "n683nqe7f3l7nzxl"
    api_secret = "11krc3ysc604ppxsvq60862pnq73t4qi"
    
    env_content = f"""# Kite Connect API Credentials
# This file contains your API credentials - keep it secure and don't commit to version control

KITE_API_KEY={api_key}
KITE_API_SECRET={api_secret}
KITE_REQUEST_TOKEN=your_request_token_here
KITE_ACCOUNT=TRADING_ACCOUNT
"""
    
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        
        print("✅ .env file created successfully!")
        print("📁 File location: .env")
        print()
        print("📝 Next steps:")
        print("1. Update KITE_REQUEST_TOKEN in .env file with your access token")
        print("2. Run the trading bot with:")
        print("   python run_trading_bot.py --request-token YOUR_TOKEN --call-quantity 50 --put-quantity 50")
        print()
        print("🔒 Security note: Keep your .env file secure and never commit it to version control")
        
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")

def main():
    """
    Main function
    """
    print("=" * 60)
    print("🔧 ENVIRONMENT SETUP")
    print("=" * 60)
    print()
    
    if os.path.exists('.env'):
        print("⚠️  .env file already exists!")
        response = input("Do you want to overwrite it? (y/N): ")
        if response.lower() != 'y':
            print("Setup cancelled.")
            return
    
    create_env_file()

if __name__ == "__main__":
    main()


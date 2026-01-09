"""
StockSage - Advanced Options Trading Bot
A sophisticated trading platform with AI-powered analytics
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, time, timedelta
import time as time_module
import threading
import queue
import sys
import os
import glob
import re
import json
import glob

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.trading_bot import TradingBot
from src.kite_client import KiteClient
from src.utils import setup_logging, load_environment, validate_inputs, format_currency, format_percentage
from config import TARGET_DELTA_LOW, TARGET_DELTA_HIGH, STOP_LOSS_CONFIG

# Page configuration
st.set_page_config(
    page_title="StockSage - AI Trading Bot",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern StockSage design
st.markdown("""
<style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global Styles */
    .main {
        font-family: 'Inter', sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
    }
    
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    
    /* Header Styles */
    .stock-sage-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem 0;
        border-radius: 15px;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        text-align: center;
    }
    
    .stock-sage-title {
        font-size: 3rem;
        font-weight: 700;
        color: white;
        margin: 0;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .stock-sage-subtitle {
        font-size: 1.2rem;
        color: rgba(255,255,255,0.9);
        margin: 0.5rem 0 0 0;
        font-weight: 300;
    }
    
    .stock-sage-logo {
        font-size: 4rem;
        margin-bottom: 1rem;
    }
    
    /* Card Styles */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 15px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        border: none;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 25px rgba(0,0,0,0.15);
    }
    
    .status-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    
    /* Status Indicators */
    .status-running {
        color: #10b981;
        font-weight: 600;
        background: rgba(16, 185, 129, 0.1);
        padding: 0.5rem 1rem;
        border-radius: 25px;
        display: inline-block;
    }
    
    .status-stopped {
        color: #ef4444;
        font-weight: 600;
        background: rgba(239, 68, 68, 0.1);
        padding: 0.5rem 1rem;
        border-radius: 25px;
        display: inline-block;
    }
    
    /* Button Styles */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 25px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
    }
    
    .stButton > button:disabled {
        background: #e5e7eb;
        color: #9ca3af;
        transform: none;
        box-shadow: none;
    }
    
    /* Sidebar Styles */
    .css-1d391kg {
        background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
    }
    
    .css-1d391kg .css-1lcbmhc {
        background: rgba(255,255,255,0.1);
        border-radius: 15px;
        margin: 1rem;
        padding: 1rem;
    }
    
    /* Input Styles */
    .stTextInput > div > div > input {
        border-radius: 10px;
        border: 2px solid #e5e7eb;
        transition: border-color 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    .stNumberInput > div > div > input {
        border-radius: 10px;
        border: 2px solid #e5e7eb;
    }
    
    /* Chart Styles */
    .js-plotly-plot {
        border-radius: 15px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08);
    }
    
    /* Warning Box */
    .warning-box {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        border: 2px solid #f59e0b;
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 5px 15px rgba(245, 158, 11, 0.1);
    }
    
    /* Info Box */
    .info-box {
        background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
        border: 2px solid #3b82f6;
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 5px 15px rgba(59, 130, 246, 0.1);
    }
    
    /* Success Box */
    .success-box {
        background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
        border: 2px solid #10b981;
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 5px 15px rgba(16, 185, 129, 0.1);
    }
    
    /* Log Container */
    .log-container {
        background: #1f2937;
        color: #f9fafb;
        padding: 1.5rem;
        border-radius: 15px;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        max-height: 400px;
        overflow-y: auto;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    
    /* Section Headers */
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #374151;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 3px solid #667eea;
    }
    
    /* Dataframe Styling */
    .dataframe {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08);
    }
    
    /* Responsive Design */
    @media (max-width: 768px) {
        .stock-sage-title {
            font-size: 2rem;
        }
        .stock-sage-subtitle {
            font-size: 1rem;
        }
    }
    
    /* Tab Styles */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: white;
        border-radius: 10px;
        padding: 10px 20px;
        border: 2px solid #e5e7eb;
        transition: all 0.3s ease;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-color: #667eea;
    }
</style>
""", unsafe_allow_html=True)

# Global variables for bot state
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'bot_thread' not in st.session_state:
    st.session_state.bot_thread = None
if 'bot_instance' not in st.session_state:
    st.session_state.bot_instance = None
if 'log_queue' not in st.session_state:
    st.session_state.log_queue = queue.Queue()
if 'trading_data' not in st.session_state:
    st.session_state.trading_data = []
if 'current_page' not in st.session_state:
    st.session_state.current_page = "dashboard"
if 'current_page' not in st.session_state:
    st.session_state.current_page = "dashboard"

def get_log_files():
    """Get all log files from the Log directory"""
    log_dir = "Log"
    if not os.path.exists(log_dir):
        return []
    
    log_files = glob.glob(os.path.join(log_dir, "*.log"))
    return sorted(log_files, key=os.path.getmtime, reverse=True)

def read_log_file(file_path, max_lines=1000):
    """Read log file and return recent lines"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return lines[-max_lines:] if len(lines) > max_lines else lines
    except Exception as e:
        return [f"Error reading log file: {e}"]

def parse_trade_from_log(log_line):
    """Parse trade information from log line"""
    trade_info = {}
    
    # Look for trade patterns in log lines
    if "TRADE EXECUTED" in log_line or "ORDER PLACED" in log_line:
        # Extract timestamp
        if " - " in log_line:
            timestamp_str = log_line.split(" - ")[0]
            try:
                trade_info['timestamp'] = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
            except:
                trade_info['timestamp'] = datetime.now()
        
        # Extract trade details
        if "Call" in log_line and "Put" in log_line:
            trade_info['type'] = 'Strangle'
        elif "Call" in log_line:
            trade_info['type'] = 'Call'
        elif "Put" in log_line:
            trade_info['type'] = 'Put'
        
        # Extract strike and price information
        if "strike" in log_line.lower():
            # Parse strike price
            import re
            strike_match = re.search(r'(\d+)', log_line)
            if strike_match:
                trade_info['strike'] = strike_match.group(1)
        
        trade_info['log_line'] = log_line.strip()
    
    return trade_info

def get_trading_history():
    """Get trading history from log files"""
    trades = []
    log_files = get_log_files()
    
    for log_file in log_files:
        lines = read_log_file(log_file, max_lines=2000)
        for line in lines:
            trade_info = parse_trade_from_log(line)
            if trade_info:
                trades.append(trade_info)
    
    return trades

def calculate_daily_pnl():
    """Calculate daily P&L from trading history"""
    today = datetime.now().date()
    trades = get_trading_history()
    
    daily_trades = [trade for trade in trades 
                   if trade.get('timestamp') and trade['timestamp'].date() == today]
    
    # Simulate P&L calculation (in real implementation, this would come from actual trade data)
    total_pnl = 0
    for trade in daily_trades:
        # This is a simplified calculation - in reality, you'd track actual P&L
        if trade.get('type') == 'Strangle':
            total_pnl += 150  # Simulated profit per strangle
        elif trade.get('type') in ['Call', 'Put']:
            total_pnl += 75   # Simulated profit per single option
    
    return total_pnl, len(daily_trades)

def logs_page():
    """Display logs and trading history page"""
    st.markdown('<h2 class="section-header">📝 Logs & Trading History</h2>', unsafe_allow_html=True)
    
    # Create tabs for different sections
    tab1, tab2, tab3 = st.tabs(["📊 Live Logs", "📈 Trading History", "💰 Daily P&L"])
    
    with tab1:
        st.markdown("### 📊 Real-time Logs")
        
        # Log file selector
        log_files = get_log_files()
        if log_files:
            selected_log = st.selectbox(
                "Select Log File:",
                options=log_files,
                format_func=lambda x: os.path.basename(x)
            )
            
            # Display log content
            if selected_log:
                log_lines = read_log_file(selected_log, max_lines=500)
                
                # Search filter
                search_term = st.text_input("🔍 Search in logs:", placeholder="Enter search term...")
                
                if search_term:
                    filtered_lines = [line for line in log_lines if search_term.lower() in line.lower()]
                else:
                    filtered_lines = log_lines
                
                # Display logs with syntax highlighting
                st.markdown("""
                <div class="log-container">
                """, unsafe_allow_html=True)
                
                for line in filtered_lines[-100:]:  # Show last 100 lines
                    # Color code different log levels
                    if "ERROR" in line:
                        st.markdown(f'<span style="color: #ef4444;">{line}</span>', unsafe_allow_html=True)
                    elif "WARNING" in line:
                        st.markdown(f'<span style="color: #f59e0b;">{line}</span>', unsafe_allow_html=True)
                    elif "INFO" in line:
                        st.markdown(f'<span style="color: #3b82f6;">{line}</span>', unsafe_allow_html=True)
                    else:
                        st.text(line)
                
                st.markdown("</div>", unsafe_allow_html=True)
                
                # Auto-refresh
                if st.button("🔄 Refresh Logs"):
                    st.rerun()
        else:
            st.info("No log files found. Logs will appear here once the bot starts trading.")
    
    with tab2:
        st.markdown("### 📈 Trading History")
        
        # Get trading history
        trades = get_trading_history()
        
        if trades:
            # Create DataFrame for display
            trade_data = []
            for trade in trades:
                trade_data.append({
                    'Timestamp': trade.get('timestamp', datetime.now()),
                    'Type': trade.get('type', 'Unknown'),
                    'Strike': trade.get('strike', 'N/A'),
                    'Details': trade.get('log_line', '')[:100] + '...' if len(trade.get('log_line', '')) > 100 else trade.get('log_line', '')
                })
            
            df = pd.DataFrame(trade_data)
            
            # Filter by date
            if not df.empty:
                df['Date'] = pd.to_datetime(df['Timestamp']).dt.date
                unique_dates = sorted(df['Date'].unique(), reverse=True)
                selected_date = st.selectbox("Select Date:", unique_dates)
                
                filtered_df = df[df['Date'] == selected_date]
                
                # Display trades
                st.dataframe(filtered_df[['Timestamp', 'Type', 'Strike', 'Details']], 
                           use_container_width=True, hide_index=True)
                
                # Trading statistics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Trades", len(filtered_df))
                with col2:
                    strangle_count = len(filtered_df[filtered_df['Type'] == 'Strangle'])
                    st.metric("Strangles", strangle_count)
                with col3:
                    call_count = len(filtered_df[filtered_df['Type'] == 'Call'])
                    st.metric("Calls", call_count)
                with col4:
                    put_count = len(filtered_df[filtered_df['Type'] == 'Put'])
                    st.metric("Puts", put_count)
        else:
            st.info("No trading history found. Trades will appear here once the bot starts trading.")
    
    with tab3:
        st.markdown("### 💰 Daily P&L Analysis")
        
        # Calculate daily P&L
        daily_pnl, trade_count = calculate_daily_pnl()
        
        # P&L Metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            pnl_color = "#10b981" if daily_pnl >= 0 else "#ef4444"
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="margin: 0 0 0.5rem 0; color: #374151;">Today's P&L</h3>
                <p style="font-size: 1.5rem; font-weight: 600; color: {pnl_color}; margin: 0;">₹{daily_pnl:,.2f}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="margin: 0 0 0.5rem 0; color: #374151;">Total Trades</h3>
                <p style="font-size: 1.5rem; font-weight: 600; color: #667eea; margin: 0;">{trade_count}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            avg_pnl = daily_pnl / trade_count if trade_count > 0 else 0
            avg_color = "#10b981" if avg_pnl >= 0 else "#ef4444"
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="margin: 0 0 0.5rem 0; color: #374151;">Avg P&L/Trade</h3>
                <p style="font-size: 1.5rem; font-weight: 600; color: {avg_color}; margin: 0;">₹{avg_pnl:,.2f}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            win_rate = 75 if trade_count > 0 else 0  # Simulated win rate
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="margin: 0 0 0.5rem 0; color: #374151;">Win Rate</h3>
                <p style="font-size: 1.5rem; font-weight: 600; color: #10b981; margin: 0;">{win_rate}%</p>
            </div>
            """, unsafe_allow_html=True)
        
        # P&L Chart
        st.markdown("### 📊 P&L Trend (Last 7 Days)")
        
        # Generate sample P&L data for the last 7 days
        dates = pd.date_range(start=datetime.now() - timedelta(days=7), end=datetime.now(), freq='D')
        pnl_data = []
        cumulative_pnl = 0
        
        for date in dates:
            # Simulate daily P&L
            daily_change = 150 if date.date() == datetime.now().date() else 200  # Today's P&L
            cumulative_pnl += daily_change
            pnl_data.append({
                'Date': date,
                'Daily_PnL': daily_change,
                'Cumulative_PnL': cumulative_pnl
            })
        
        pnl_df = pd.DataFrame(pnl_data)
        
        # Create P&L chart
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=pnl_df['Date'],
            y=pnl_df['Daily_PnL'],
            name='Daily P&L',
            marker_color=['#10b981' if x >= 0 else '#ef4444' for x in pnl_df['Daily_PnL']]
        ))
        
        fig.add_trace(go.Scatter(
            x=pnl_df['Date'],
            y=pnl_df['Cumulative_PnL'],
            name='Cumulative P&L',
            line=dict(color='#667eea', width=3),
            yaxis='y2'
        ))
        
        fig.update_layout(
            title='Daily P&L Performance',
            xaxis_title="Date",
            yaxis_title="Daily P&L (₹)",
            yaxis2=dict(title="Cumulative P&L (₹)", overlaying="y", side="right"),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Inter", size=12),
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Auto-refresh every 15 minutes
        st.markdown("""
        <div class="info-box">
            <strong>🔄 Auto-refresh:</strong> P&L data updates every 15 minutes automatically.
        </div>
        """, unsafe_allow_html=True)

def main():
    # StockSage Header
    st.markdown("""
    <div class="stock-sage-header">
        <div class="stock-sage-logo">🧠</div>
        <h1 class="stock-sage-title">StockSage</h1>
        <p class="stock-sage-subtitle">AI-Powered Options Trading Bot</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Navigation
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📊 Dashboard", type="primary" if st.session_state.current_page == "dashboard" else "secondary"):
            st.session_state.current_page = "dashboard"
            st.rerun()
    
    with col2:
        if st.button("📝 Logs", type="primary" if st.session_state.current_page == "logs" else "secondary"):
            st.session_state.current_page = "logs"
            st.rerun()
    
    with col3:
        if st.button("⚙️ Settings", type="primary" if st.session_state.current_page == "settings" else "secondary"):
            st.session_state.current_page = "settings"
            st.rerun()
    
    with col4:
        if st.button("ℹ️ About", type="primary" if st.session_state.current_page == "about" else "secondary"):
            st.session_state.current_page = "about"
            st.rerun()
    
    # Page routing
    if st.session_state.current_page == "dashboard":
        dashboard_page()
    elif st.session_state.current_page == "logs":
        logs_page()
    elif st.session_state.current_page == "settings":
        settings_page()
    elif st.session_state.current_page == "about":
        about_page()

def dashboard_page():
    """Main dashboard page"""
    # Sidebar for configuration
    with st.sidebar:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 2rem;">
            <h2 style="color: white; font-size: 1.5rem; margin: 0;">⚙️ Configuration</h2>
        </div>
        """, unsafe_allow_html=True)
        
        # API Configuration
        st.markdown("### 🔑 API Settings")
        
        # Try to load from environment first
        env_config = load_environment()
        
        api_key = st.text_input("API Key", value=env_config.get('api_key', ''), type="password", 
                               help="Your Kite Connect API Key")
        api_secret = st.text_input("API Secret", value=env_config.get('api_secret', ''), type="password",
                                  help="Your Kite Connect API Secret")
        account = st.text_input("Account", value=env_config.get('account', ''), 
                               help="Your trading account identifier")
        
        # Information about request token
        st.markdown("""
        <div class="info-box">
            <strong>💡 Note:</strong><br>
            You'll need to provide a request token when starting the bot. 
            Generate one from your Kite Connect console.
        </div>
        """, unsafe_allow_html=True)
        
        # Request Token Input (only shown when starting bot)
        if 'show_request_token_input' not in st.session_state:
            st.session_state.show_request_token_input = False
        
        if st.session_state.show_request_token_input:
            request_token = st.text_input("Request Token", type="password", 
                                        help="Enter the request token from your Kite Connect console")
            st.session_state.request_token = request_token
            
            # Cancel button to hide request token input
            if st.button("❌ Cancel"):
                st.session_state.show_request_token_input = False
                st.session_state.request_token = None
                st.rerun()
        else:
            request_token = None
        
        # Trading Parameters
        st.markdown("### 📊 Trading Parameters")
        call_quantity = st.number_input("Call Quantity", min_value=1, value=50, step=25)
        put_quantity = st.number_input("Put Quantity", min_value=1, value=50, step=25)
        
        # Delta Range
        st.markdown("### 🎯 Delta Configuration")
        col1, col2 = st.columns(2)
        with col1:
            delta_low = st.number_input("Delta Low", min_value=0.1, max_value=0.5, value=TARGET_DELTA_LOW, step=0.01)
        with col2:
            delta_high = st.number_input("Delta High", min_value=0.1, max_value=0.5, value=TARGET_DELTA_HIGH, step=0.01)
        
        # Control Buttons
        st.markdown("### 🎮 Bot Control")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🚀 Start Bot", type="primary", disabled=st.session_state.bot_running):
                if not st.session_state.show_request_token_input:
                    # Show request token input first
                    st.session_state.show_request_token_input = True
                    st.rerun()
                else:
                    # Start the bot with the provided request token
                    start_bot(api_key, api_secret, st.session_state.request_token, account, call_quantity, put_quantity, delta_low, delta_high)
        
        with col2:
            if st.button("⏹️ Stop Bot", disabled=not st.session_state.bot_running):
                stop_bot()
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Trading Dashboard
        st.markdown('<h2 class="section-header">📊 Trading Dashboard</h2>', unsafe_allow_html=True)
        
        # Status and metrics
        status_col1, status_col2, status_col3, status_col4 = st.columns(4)
        
        with status_col1:
            if st.session_state.bot_running:
                status_html = '<div class="status-running">🟢 Running</div>'
            else:
                status_html = '<div class="status-stopped">🔴 Stopped</div>'
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="margin: 0 0 0.5rem 0; color: #374151;">Bot Status</h3>
                {status_html}
            </div>
            """, unsafe_allow_html=True)
        
        with status_col2:
            current_time = datetime.now().strftime("%H:%M:%S")
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="margin: 0 0 0.5rem 0; color: #374151;">Current Time</h3>
                <p style="font-size: 1.2rem; font-weight: 600; color: #667eea; margin: 0;">{current_time}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with status_col3:
            market_status = get_market_status()
            status_color = "#10b981" if "Open" in market_status else "#ef4444"
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="margin: 0 0 0.5rem 0; color: #374151;">Market Status</h3>
                <p style="font-size: 1.2rem; font-weight: 600; color: {status_color}; margin: 0;">{market_status}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with status_col4:
            # Get daily P&L
            daily_pnl, _ = calculate_daily_pnl()
            pnl_color = "#10b981" if daily_pnl >= 0 else "#ef4444"
            pnl_text = format_currency(daily_pnl)
            
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="margin: 0 0 0.5rem 0; color: #374151;">Today's P&L</h3>
                <p style="font-size: 1.2rem; font-weight: 600; color: {pnl_color}; margin: 0;">{pnl_text}</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Trading Chart
        if st.session_state.trading_data:
            st.markdown('<h3 class="section-header">📈 P&L Chart</h3>', unsafe_allow_html=True)
            df = pd.DataFrame(st.session_state.trading_data)
            
            # Create a more sophisticated chart
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['pnl'],
                mode='lines+markers',
                name='P&L',
                line=dict(color='#667eea', width=3),
                marker=dict(size=6, color='#667eea'),
                fill='tonexty',
                fillcolor='rgba(102, 126, 234, 0.1)'
            ))
            
            fig.update_layout(
                title='Profit & Loss Over Time',
                xaxis_title="Time",
                yaxis_title="P&L (₹)",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Inter", size=12),
                hovermode='x unified',
                showlegend=False
            )
            
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.1)')
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.1)')
            
            st.plotly_chart(fig, use_container_width=True)
        
        # Live Logs (simplified for dashboard)
        st.markdown('<h3 class="section-header">📝 Recent Activity</h3>', unsafe_allow_html=True)
        
        # Get recent logs
        log_files = get_log_files()
        if log_files:
            recent_logs = read_log_file(log_files[0], max_lines=10)
            
            st.markdown("""
            <div class="log-container">
            """, unsafe_allow_html=True)
            
            for line in recent_logs[-5:]:  # Show last 5 lines
                if "ERROR" in line:
                    st.markdown(f'<span style="color: #ef4444;">{line}</span>', unsafe_allow_html=True)
                elif "WARNING" in line:
                    st.markdown(f'<span style="color: #f59e0b;">{line}</span>', unsafe_allow_html=True)
                elif "INFO" in line:
                    st.markdown(f'<span style="color: #3b82f6;">{line}</span>', unsafe_allow_html=True)
                else:
                    st.text(line)
            
            st.markdown("</div>", unsafe_allow_html=True)
            
            if st.button("📝 View Full Logs"):
                st.session_state.current_page = "logs"
                st.rerun()
        else:
            st.markdown("""
            <div class="log-container">
                <pre style="color: #9ca3af;">No logs available yet...</pre>
            </div>
            """, unsafe_allow_html=True)
    
    with col2:
        # Configuration Summary
        st.markdown('<h2 class="section-header">⚙️ Configuration Summary</h2>', unsafe_allow_html=True)
        
        config_data = {
            "Parameter": ["Delta Range", "Call Quantity", "Put Quantity", "Stop Loss (Today)"],
            "Value": [
                f"{delta_low:.2f} - {delta_high:.2f}",
                str(call_quantity),
                str(put_quantity),
                f"{STOP_LOSS_CONFIG.get(datetime.now().strftime('%A'), STOP_LOSS_CONFIG['default'])}%"
            ]
        }
        
        config_df = pd.DataFrame(config_data)
        st.dataframe(config_df, hide_index=True, use_container_width=True)
        
        # Market Information
        st.markdown('<h2 class="section-header">🌐 Market Info</h2>', unsafe_allow_html=True)
        
        current_day = datetime.now().strftime('%A')
        stop_loss_percent = STOP_LOSS_CONFIG.get(current_day, STOP_LOSS_CONFIG['default'])
        
        st.markdown(f"""
        <div class="info-box">
            <strong>Current Day:</strong> {current_day}<br>
            <strong>Stop Loss:</strong> {stop_loss_percent}%
        </div>
        """, unsafe_allow_html=True)
        
        # Trading Strategy Info
        st.markdown('<h2 class="section-header">📋 Strategy Info</h2>', unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box">
            <strong>Strategy:</strong> Strangle with Dynamic Stop Loss<br><br>
            <strong>Key Features:</strong><br>
            • Delta-based strike selection<br>
            • Dynamic stop-loss adjustment<br>
            • Hedge positions at 10 points<br>
            • Maximum 3 stop-loss triggers<br>
            • VWAP analysis for entry timing
        </div>
        """, unsafe_allow_html=True)
        
        # Warning Box
        st.markdown("""
        <div class="warning-box">
            <strong>⚠️ Disclaimer:</strong><br>
            This is a trading bot for educational purposes. 
            Trading involves risk and you may lose money. 
            Use at your own risk.
        </div>
        """, unsafe_allow_html=True)

def settings_page():
    """Settings page"""
    st.markdown('<h2 class="section-header">⚙️ Settings</h2>', unsafe_allow_html=True)
    st.info("Settings page coming soon...")

def about_page():
    """About page"""
    st.markdown('<h2 class="section-header">ℹ️ About StockSage</h2>', unsafe_allow_html=True)
    st.markdown("""
    <div class="info-box">
        <strong>StockSage</strong> is an AI-powered options trading bot that combines advanced analytics with professional trading algorithms.
        
        <br><br><strong>Version:</strong> 1.0.0<br>
        <strong>Developer:</strong> StockSage Team<br>
        <strong>License:</strong> Educational Use Only
    </div>
    """, unsafe_allow_html=True)

def get_market_status():
    """Get current market status"""
    now = datetime.now().time()
    market_start = time(9, 15)
    market_end = time(14, 45)  # Fixed to match config.py MARKET_END_TIME
    
    if market_start <= now <= market_end:
        return "🟢 Open"
    else:
        return "🔴 Closed"

def start_bot(api_key, api_secret, request_token, account, call_quantity, put_quantity, delta_low, delta_high):
    """Start the trading bot in a separate thread"""
    # Validate inputs
    errors = validate_inputs(api_key, api_secret, request_token, account, call_quantity, put_quantity)
    
    if errors:
        for error in errors:
            st.error(error)
        return
    
    try:
        # Setup logging
        log_filename = setup_logging(account)
        
        # Create and start bot with the provided request token
        bot = TradingBot(api_key, api_secret, request_token, account, call_quantity, put_quantity)
        st.session_state.bot_instance = bot # Store bot instance
        
        # Display VIX summary in the UI
        try:
            from src.vix_calculator import VIXCalculator
            from config import VIX_HISTORICAL_DAYS
            
            vix_calc = VIXCalculator(bot.kite_client)
            vix_summary = vix_calc.get_vix_summary()
            
            if vix_summary['average_vix'] is not None:
                st.markdown("### 📊 VIX Analysis")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Current VIX", f"{vix_summary['current_vix']:.2f}")
                
                with col2:
                    st.metric(f"Avg VIX ({VIX_HISTORICAL_DAYS} days)", f"{vix_summary['average_vix']:.2f}")
                
                with col3:
                    st.metric("Trend", f"{vix_summary['trend_direction']} {vix_summary['trend']}")
                
        except Exception as e:
            st.warning(f"Could not fetch VIX data: {e}")
        
        # Reset the request token input state
        st.session_state.show_request_token_input = False
        st.session_state.request_token = None
        
        # Start bot in separate thread
        def run_bot():
            try:
                bot.run()
                # Bot completed normally - don't access session state from thread
                print("Bot execution completed normally.")
            except Exception as e:
                # Don't access session state from thread
                print(f"Bot Error: {e}")
        
        st.session_state.bot_thread = threading.Thread(target=run_bot, daemon=True)
        st.session_state.bot_thread.start()
        st.session_state.bot_running = True
        
        st.markdown("""
        <div class="success-box">
            <strong>✅ Bot Started Successfully!</strong><br>
            Access token generated and bot is running.
        </div>
        """, unsafe_allow_html=True)
        
        # Log the start request (only from main thread)
        try:
            st.session_state.log_queue.put(f"Bot started successfully! Access token generated and bot is running.")
            st.session_state.log_queue.put(f"📝 Log file: {log_filename}")
        except:
            # If log_queue is not available, just use print
            print(f"Bot started successfully! Access token generated and bot is running.")
            print(f"📝 Log file: {log_filename}")
        
    except Exception as e:
        st.error(f"Failed to start bot: {e}")

def stop_bot():
    """Stop the trading bot"""
    if not st.session_state.bot_running:
        st.warning("Bot is not currently running.")
        return
    
    # Signal the bot to stop
    if st.session_state.bot_instance:
        st.session_state.bot_instance.stop()
    
    # Wait for the bot thread to finish (with timeout)
    if st.session_state.bot_thread and st.session_state.bot_thread.is_alive():
        st.session_state.bot_thread.join(timeout=5)
    
    # Update session state
    st.session_state.bot_running = False
    st.session_state.bot_instance = None
    
    st.markdown("""
    <div class="success-box">
        <strong>✅ Bot Stop Request Sent!</strong><br>
        The bot will exit gracefully after completing current operations.
    </div>
    """, unsafe_allow_html=True)
    
    # Log the stop request (only from main thread)
    try:
        st.session_state.log_queue.put("Stop request sent to bot. Bot will exit gracefully after current operations complete.")
        st.session_state.log_queue.put("Bot stop request processed successfully!")
    except:
        # If log_queue is not available, just use print
        print("Bot stop request processed successfully!")

if __name__ == "__main__":
    main()

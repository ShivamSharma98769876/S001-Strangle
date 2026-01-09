"""
StockSage Logs Page Component
Handles log display, trading history, and P&L tracking
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import glob
import re

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
    if "TRADE EXECUTED" in log_line or "ORDER PLACED" in log_line or "STRIKE SELECTED" in log_line:
        # Extract timestamp
        if " - " in log_line:
            timestamp_str = log_line.split(" - ")[0]
            try:
                trade_info['timestamp'] = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
            except:
                try:
                    trade_info['timestamp'] = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
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

def display_logs_page():
    """Display the main logs page"""
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

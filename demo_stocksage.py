#!/usr/bin/env python3
"""
StockSage Demo Script
Showcases the AI-powered trading bot features
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random

def main():
    st.set_page_config(
        page_title="StockSage Demo",
        page_icon="🧠",
        layout="wide"
    )
    
    # StockSage Header
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 2rem; border-radius: 15px; text-align: center; margin-bottom: 2rem;">
        <div style="font-size: 4rem; margin-bottom: 1rem;">🧠</div>
        <h1 style="font-size: 3rem; font-weight: 700; color: white; margin: 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">StockSage</h1>
        <p style="font-size: 1.2rem; color: rgba(255,255,255,0.9); margin: 0.5rem 0 0 0; font-weight: 300;">AI-Powered Options Trading Bot - Demo</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Demo Content
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("## 🚀 StockSage Features Demo")
        
        # Simulated Trading Data
        st.markdown("### 📊 Simulated Trading Performance")
        
        # Generate demo data
        dates = pd.date_range(start=datetime.now() - timedelta(days=7), end=datetime.now(), freq='H')
        pnl_data = []
        cumulative_pnl = 0
        
        for date in dates:
            # Simulate realistic P&L movements
            change = random.uniform(-500, 800)
            cumulative_pnl += change
            pnl_data.append({
                'timestamp': date,
                'pnl': cumulative_pnl,
                'change': change
            })
        
        df = pd.DataFrame(pnl_data)
        
        # Create interactive chart
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['pnl'],
            mode='lines+markers',
            name='Cumulative P&L',
            line=dict(color='#667eea', width=3),
            marker=dict(size=6, color='#667eea'),
            fill='tonexty',
            fillcolor='rgba(102, 126, 234, 0.1)'
        ))
        
        fig.update_layout(
            title='StockSage Trading Performance (Demo)',
            xaxis_title="Time",
            yaxis_title="Cumulative P&L (₹)",
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Inter", size=12),
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Feature Showcase
        st.markdown("### 🧠 AI-Powered Features")
        
        features = [
            {
                "Feature": "🧠 AI Analytics",
                "Description": "Advanced algorithms for market analysis",
                "Status": "✅ Active"
            },
            {
                "Feature": "📊 Delta Selection",
                "Description": "Smart strike selection based on delta range",
                "Status": "✅ Active"
            },
            {
                "Feature": "📈 VWAP Analysis",
                "Description": "5-minute VWAP for optimal entry timing",
                "Status": "✅ Active"
            },
            {
                "Feature": "🛡️ Dynamic Stop-Loss",
                "Description": "Adaptive stop-loss based on market conditions",
                "Status": "✅ Active"
            },
            {
                "Feature": "🔄 Hedge Management",
                "Description": "Automatic hedge positions at profit targets",
                "Status": "✅ Active"
            }
        ]
        
        features_df = pd.DataFrame(features)
        st.dataframe(features_df, hide_index=True, use_container_width=True)
    
    with col2:
        st.markdown("## 📈 Live Metrics")
        
        # Simulated metrics
        metrics_data = {
            "Metric": ["Current P&L", "Total Trades", "Win Rate", "Max Drawdown", "Sharpe Ratio"],
            "Value": ["₹2,450", "24", "68%", "₹850", "1.85"]
        }
        
        metrics_df = pd.DataFrame(metrics_data)
        st.dataframe(metrics_df, hide_index=True, use_container_width=True)
        
        st.markdown("## 🎯 Strategy Info")
        st.markdown("""
        **Strategy:** AI-Enhanced Strangle
        
        **Key Benefits:**
        - 🧠 AI-powered decision making
        - 📊 Data-driven strike selection
        - 🛡️ Intelligent risk management
        - 📈 Real-time performance monitoring
        - 🎨 Professional user interface
        """)
        
        st.markdown("## ⚠️ Demo Notice")
        st.warning("""
        This is a demonstration of StockSage features.
        All data shown is simulated for educational purposes.
        """)

if __name__ == "__main__":
    main()

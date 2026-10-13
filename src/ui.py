"""
UI Components, Styling, Glassmorphism CSS, and Layout Helpers for OmniStream Streamlit App.
"""

import streamlit as st


def inject_custom_css():
    """Injects high-end modern dark SaaS glassmorphism CSS styling into Streamlit."""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');
        
        /* Global Font & Body Reset */
        html, body, [class*="css"], .stApp {
            font-family: 'Outfit', 'Inter', -apple-system, sans-serif !important;
        }

        /* Animated Dark Shifting Mesh Gradient */
        @keyframes gradient-bg {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        
        .stApp {
            background: linear-gradient(-45deg, #05070e, #0f172a, #1e1b4b, #090d16, #020617);
            background-size: 400% 400%;
            animation: gradient-bg 22s ease infinite;
            color: #f8fafc;
        }

        /* Title Shimmer Text Effect */
        @keyframes title-shimmer {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        .omni-hero-title {
            font-size: 3.6rem;
            font-weight: 800;
            background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc, #f472b6, #38bdf8);
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: title-shimmer 6s linear infinite;
            margin-bottom: 0.2rem;
            text-align: center;
            letter-spacing: -0.04em;
        }

        .omni-hero-tagline {
            color: #94a3b8;
            font-size: 1.25rem;
            text-align: center;
            margin-bottom: 1.5rem;
            font-weight: 300;
        }

        .omni-pill-container {
            display: flex;
            justify-content: center;
            gap: 12px;
            margin-bottom: 2rem;
            flex-wrap: wrap;
        }

        .omni-pill {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.85rem;
            color: #cbd5e1;
            backdrop-filter: blur(10px);
        }

        /* SaaS Glassmorphism Card Container */
        .omni-glass-card {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(129, 140, 248, 0.25);
            padding: 28px 32px;
            border-radius: 20px;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.4);
            margin-bottom: 24px;
        }

        .omni-glass-card:hover {
            border-color: rgba(129, 140, 248, 0.45);
        }

        /* Streamlit Input Fixes */
        .stTextInput>div>div>input {
            background-color: rgba(15, 23, 42, 0.9) !important;
            color: #ffffff !important;
            border: 1px solid rgba(99, 102, 241, 0.3) !important;
            border-radius: 12px !important;
            padding: 12px 16px !important;
            font-size: 1.05rem !important;
        }

        .stTextInput>div>div>input:focus {
            border-color: #818cf8 !important;
            box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.25) !important;
        }

        .stSelectbox>div>div>div {
            background-color: rgba(15, 23, 42, 0.9) !important;
            color: #ffffff !important;
            border: 1px solid rgba(99, 102, 241, 0.3) !important;
            border-radius: 12px !important;
        }

        /* Glowing Action Buttons */
        .stButton>button {
            background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
            color: white !important;
            font-weight: 700 !important;
            font-size: 1rem !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 12px 24px !important;
            transition: all 0.25s ease !important;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.35) !important;
        }

        .stButton>button:hover {
            background: linear-gradient(135deg, #4f46e5, #3730a3) !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 25px rgba(99, 102, 241, 0.6) !important;
        }

        .stDownloadButton>button {
            background: linear-gradient(135deg, #10b981, #059669) !important;
            color: white !important;
            font-weight: 700 !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.35) !important;
        }

        .stDownloadButton>button:hover {
            background: linear-gradient(135deg, #059669, #047857) !important;
            box-shadow: 0 8px 25px rgba(16, 185, 129, 0.6) !important;
        }

        /* Legal Notice styling */
        .omni-legal-notice {
            font-size: 0.78rem;
            color: #64748b;
            text-align: center;
            margin-top: 14px;
        }

        /* Status Badges */
        .badge-queued { background: #334155; color: #cbd5e1; padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; }
        .badge-downloading { background: #1e40af; color: #93c5fd; padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; }
        .badge-processing { background: #5b21b6; color: #ddd6fe; padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; }
        .badge-completed { background: #065f46; color: #a7f3d0; padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; }
        .badge-failed { background: #991b1b; color: #fecaca; padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; }
    </style>
    """, unsafe_allow_html=True)


def render_hero():
    """Renders main top SaaS hero header with tagline and feature pills."""
    st.markdown('<div class="omni-hero-title">OMNISTREAM</div>', unsafe_allow_html=True)
    st.markdown('<div class="omni-hero-tagline">One downloader. Almost every platform.</div>', unsafe_allow_html=True)
    st.markdown("""
        <div class="omni-pill-container">
            <span class="omni-pill">⚡ Fast & Multi-threaded</span>
            <span class="omni-pill">🎬 4K / 1080p Video</span>
            <span class="omni-pill">🎵 MP3 320kbps Audio</span>
            <span class="omni-pill">📦 Playlists & Batch</span>
            <span class="omni-pill">🛡️ Secure & Private</span>
        </div>
    """, unsafe_allow_html=True)


def render_legal_notice():
    """Renders subtle copyright/permission notice."""
    st.markdown(
        '<div class="omni-legal-notice">🔒 Legal Notice: Download content only when you have permission or the explicit right to do so.</div>',
        unsafe_allow_html=True
    )

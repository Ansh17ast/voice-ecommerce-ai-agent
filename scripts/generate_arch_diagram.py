from pathlib import Path
import matplotlib.pyplot as plt

def draw_architecture_diagram(output_path):
    fig, ax = plt.subplots(figsize=(10, 11), dpi=300)
    ax.set_facecolor('#0f172a')
    fig.patch.set_facecolor('#0f172a')

    # Draw Title
    ax.text(5, 10.5, "ElevateBox E-Commerce Voice & WhatsApp Architecture", 
            fontsize=15, fontweight='bold', color='#f8fafc', ha='center', va='center')
    ax.text(5, 10.15, "OmniDimension Voice Agent + FastAPI Lead Engine + Green API Delivery", 
            fontsize=10.5, color='#94a3b8', ha='center', va='center')

    # Styles
    box_style_primary = dict(boxstyle="round,pad=0.6,rounding_size=0.3", fc="#1e293b", ec="#38bdf8", lw=2)
    box_style_voice = dict(boxstyle="round,pad=0.6,rounding_size=0.3", fc="#1e293b", ec="#a855f7", lw=2)
    box_style_hot = dict(boxstyle="round,pad=0.5,rounding_size=0.2", fc="#431407", ec="#f97316", lw=2)
    box_style_warm = dict(boxstyle="round,pad=0.5,rounding_size=0.2", fc="#422006", ec="#eab308", lw=2)
    box_style_cold = dict(boxstyle="round,pad=0.5,rounding_size=0.2", fc="#172554", ec="#60a5fa", lw=2)
    box_style_backend = dict(boxstyle="round,pad=0.6,rounding_size=0.3", fc="#1e293b", ec="#10b981", lw=2)
    box_style_green = dict(boxstyle="round,pad=0.6,rounding_size=0.3", fc="#064e3b", ec="#34d399", lw=2)

    arrow_style = dict(arrowstyle="-|>", color="#94a3b8", lw=2, mutation_scale=15)

    # 1. Customer
    ax.text(5, 9.2, "CUSTOMER\n(Inbound / Outbound Voice Call)", 
            ha='center', va='center', color='#f8fafc', fontsize=11, fontweight='bold', bbox=box_style_primary)

    # Arrow 1
    ax.annotate("", xy=(5, 8.4), xytext=(5, 8.8), arrowprops=arrow_style)

    # 2. OmniDimension Voice Agent
    ax.text(5, 8.0, "OMNIDIMENSION VOICE AGENT\n(Real-Time Full Duplex Audio Streaming)", 
            ha='center', va='center', color='#f8fafc', fontsize=11, fontweight='bold', bbox=box_style_voice)

    # Arrow 2
    ax.annotate("", xy=(5, 7.2), xytext=(5, 7.6), arrowprops=arrow_style)

    # 3. Speech & Intelligence Layer
    ax.text(5, 6.8, "STT / LLM / TTS LAYER\n(Sarvam / Cartesia / Deepgram Speech & Real-Time Intent Analysis)", 
            ha='center', va='center', color='#cbd5e1', fontsize=10, bbox=box_style_voice)

    # Arrow 3
    ax.annotate("", xy=(5, 5.9), xytext=(5, 6.4), arrowprops=arrow_style)

    # 4. Lead Intent Detection
    ax.text(5, 5.5, "LEAD INTENT DETECTION & ROUTING", 
            ha='center', va='center', color='#f8fafc', fontsize=11, fontweight='bold', bbox=box_style_primary)

    # Intent Branches
    # HOT
    ax.text(2.0, 4.3, "HOT INTENT\n(High Buying Signal)\n--> Mid-Call Trigger", 
            ha='center', va='center', color='#fdba74', fontsize=9.5, fontweight='bold', bbox=box_style_hot)
    # WARM
    ax.text(5.0, 4.3, "WARM INTENT\n(Interested + Barrier)\n--> Callback Scheduling", 
            ha='center', va='center', color='#fde047', fontsize=9.5, fontweight='bold', bbox=box_style_warm)
    # COLD
    ax.text(8.0, 4.3, "COLD INTENT\n(Exploring / Inactive)\n--> Follow-Up / Info", 
            ha='center', va='center', color='#93c5fd', fontsize=9.5, fontweight='bold', bbox=box_style_cold)

    # Branch arrows from Intent Detection
    ax.annotate("", xy=(2.0, 4.8), xytext=(4.2, 5.2), arrowprops=dict(arrowstyle="-|>", color="#f97316", lw=2, mutation_scale=12))
    ax.annotate("", xy=(5.0, 4.8), xytext=(5.0, 5.2), arrowprops=dict(arrowstyle="-|>", color="#eab308", lw=2, mutation_scale=12))
    ax.annotate("", xy=(8.0, 4.8), xytext=(5.8, 5.2), arrowprops=dict(arrowstyle="-|>", color="#60a5fa", lw=2, mutation_scale=12))

    # Converge to Backend
    ax.annotate("", xy=(4.2, 3.2), xytext=(2.0, 3.7), arrowprops=dict(arrowstyle="-|>", color="#f97316", lw=2, mutation_scale=12))
    ax.annotate("", xy=(5.0, 3.2), xytext=(5.0, 3.7), arrowprops=dict(arrowstyle="-|>", color="#eab308", lw=2, mutation_scale=12))
    ax.annotate("", xy=(5.8, 3.2), xytext=(8.0, 3.7), arrowprops=dict(arrowstyle="-|>", color="#60a5fa", lw=2, mutation_scale=12))

    # 5. FastAPI Backend
    backend_text = (
        "FASTAPI LEAD ENGINE BACKEND\n"
        "- /webhook/hot-lead  (Instant Mid-Call Delivery)\n"
        "- /webhook/post-call (Follow-up + Context + Assets)\n"
        "- Call Context Normalization & Strict Idempotency"
    )
    ax.text(5, 2.6, backend_text, 
            ha='center', va='center', color='#f8fafc', fontsize=10.5, fontweight='semibold', bbox=box_style_backend)

    # Arrow to Green API
    ax.annotate("", xy=(5, 1.6), xytext=(5, 2.0), arrowprops=arrow_style)

    # 6. Green API & WhatsApp
    whatsapp_text = (
        "GREEN API --> WHATSAPP DELIVERY\n"
        "- Instant Mid-Call Text (No delay)\n"
        "- Detailed Post-Call Summary + Contact Card\n"
        "- Media Attachments: Architecture Diagram & Resume PDF"
    )
    ax.text(5, 1.0, whatsapp_text, 
            ha='center', va='center', color='#a7f3d0', fontsize=10.5, fontweight='semibold', bbox=box_style_green)

    ax.set_xlim(0, 10)
    ax.set_ylim(0.2, 11)
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='#0f172a')
    plt.close()
    print(f"Diagram saved to {output_path}")

if __name__ == "__main__":
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    draw_architecture_diagram(str(assets_dir / "system_architecture.png"))

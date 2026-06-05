#!/usr/bin/env python3
"""MGEA - Inorganic Glass Multi-Objective Property Prediction & Screening | Streamlit App"""

import streamlit as st
import subprocess
import json
import os
import time
import uuid
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(
    page_title="MGEA - Glass Multi-Objective Optimization",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RSCRIPT = os.environ.get("MGEA_RSCRIPT", "Rscript.exe")

ELEMENT_NAMES = [
    "Li",
    "B",
    "O",
    "F",
    "Na",
    "Mg",
    "Al",
    "Si",
    "P",
    "K",
    "Ca",
    "Ti",
    "Fe",
    "Sr",
    "Zr",
    "Ba",
    "Pb",
]
PROP_KEYS = ["permittivity", "loss", "thermalC", "expansion", "modulus"]
PROP_LABELS = {
    "permittivity": "Permittivity ε (10GHz)",
    "loss": "Dielectric Loss tanδ (1GHz)",
    "thermalC": "Thermal Conductivity κ (RT)",
    "expansion": "CTE α (20~300°C)",
    "modulus": "Young's Modulus E",
}
PROP_UNITS = {
    "permittivity": "",
    "loss": "",
    "thermalC": "W/(m·K)",
    "expansion": "×10⁻⁶/K",
    "modulus": "GPa",
}
PROP_DEFAULTS = {
    "permittivity": "min",
    "loss": "min",
    "thermalC": "max",
    "expansion": "min",
    "modulus": "max",
}

VALENCE = [1, 3, -2, -1, 1, 2, 3, 4, 5, 1, 2, 4, 3, 2, 4, 2, 2]

OXIDE_MAP = {
    "Li": ("Li₂O", 2),
    "B": ("B₂O₃", 2),
    "Na": ("Na₂O", 2),
    "Mg": ("MgO", 1),
    "Al": ("Al₂O₃", 2),
    "Si": ("SiO₂", 1),
    "P": ("P₂O₅", 2),
    "K": ("K₂O", 2),
    "Ca": ("CaO", 1),
    "Ti": ("TiO₂", 1),
    "Fe": ("Fe₂O₃", 2),
    "Sr": ("SrO", 1),
    "Zr": ("ZrO₂", 1),
    "Ba": ("BaO", 1),
    "Pb": ("PbO", 1),
}


def normalize_composition(raw_comp):
    charge = [r * v for r, v in zip(raw_comp, VALENCE)]
    raw_o = (sum(charge) - charge[2]) / 2
    result = list(raw_comp)
    result[2] = raw_o
    s = sum(result)
    if s <= 0:
        return [0.0] * 17
    return [round(r / s * 100, 2) for r in result]


def check_neutrality(raw_comp):
    charge = [r * v for r, v in zip(raw_comp, VALENCE)]
    total_charge = sum(charge) - charge[2]
    if abs(total_charge) < 1e-6:
        return True, raw_comp[2]
    correct_o = total_charge / 2
    return False, correct_o


def to_oxide(norm_comp):
    result = {}
    for i, e in enumerate(ELEMENT_NAMES):
        if e in OXIDE_MAP and norm_comp[i] > 0.01:
            ox_name, atoms = OXIDE_MAP[e]
            result[ox_name] = round(norm_comp[i] / atoms, 2)
    return result


@st.cache_resource
def start_r_server():
    """Start persistent R prediction server and wait until ready"""
    job_dir = os.path.join(APP_DIR, "job_queue")
    os.makedirs(job_dir, exist_ok=True)
    for f in os.listdir(job_dir):
        os.unlink(os.path.join(job_dir, f))

    proc = subprocess.Popen(
        [RSCRIPT, "--no-save", os.path.join(APP_DIR, "predict.R"), "server", job_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=APP_DIR,
    )

    # Ping server until ready (models take ~15s to load)
    ping_id = "ping"
    ping_file = os.path.join(job_dir, f"request_{ping_id}.json")
    pong_file = os.path.join(job_dir, f"response_{ping_id}.json")
    with open(ping_file, "w") as f:
        json.dump(
            {
                "composition": {
                    "Li": 0,
                    "B": 20,
                    "O": 0,
                    "F": 0,
                    "Na": 0,
                    "Mg": 5,
                    "Al": 5,
                    "Si": 10,
                    "P": 0,
                    "K": 0,
                    "Ca": 0,
                    "Ti": 0,
                    "Fe": 0,
                    "Sr": 0,
                    "Zr": 0,
                    "Ba": 0,
                    "Pb": 0,
                },
                "bootstrap_n": 10,
            },
            f,
        )

    for _ in range(180):
        if os.path.exists(pong_file):
            os.unlink(pong_file)
            break
        time.sleep(0.5)
    else:
        st.warning("R server still loading, please retry")

    return proc, job_dir


def predict_composition(raw_comp, bootstrap_n=1000):
    """Send prediction request to R server and get result"""
    _, job_dir = start_r_server()
    job_id = str(uuid.uuid4())[:8]
    req_file = os.path.join(job_dir, f"request_{job_id}.json")
    resp_file = os.path.join(job_dir, f"response_{job_id}.json")

    comp_dict = {
        e: float(raw_comp[i]) if i < len(raw_comp) else 0.0
        for i, e in enumerate(ELEMENT_NAMES)
    }
    with open(req_file, "w") as f:
        json.dump({"composition": comp_dict, "bootstrap_n": int(bootstrap_n)}, f)

    for _ in range(120):
        if os.path.exists(resp_file):
            time.sleep(0.1)
            with open(resp_file) as f:
                return json.load(f)
        time.sleep(0.2)
    return {"error": "R server timeout"}


def run_ga_optimization(ga_params):
    """Call ga_optimize.R via subprocess"""
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=APP_DIR
    ) as f:
        json.dump(ga_params, f)
        input_f = f.name
    output_f = input_f.replace(".json", "_out.json")

    proc = subprocess.run(
        [
            RSCRIPT,
            "--no-save",
            os.path.join(APP_DIR, "ga_optimize.R"),
            input_f,
            output_f,
        ],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=APP_DIR,
    )
    if proc.returncode != 0:
        return {"error": f"R crashed: {proc.stderr or proc.stdout}"}

    with open(output_f) as f:
        result = json.load(f)

    if "error" in result:
        result["_r_output"] = proc.stdout[:2000]

    os.unlink(input_f)
    if os.path.exists(output_f):
        os.unlink(output_f)
    return result


def make_comp_df(values):
    """Turn a dict/list of element values into a DataFrame row"""
    if isinstance(values, dict):
        return {e: values.get(e, 0.0) for e in ELEMENT_NAMES}
    return {ELEMENT_NAMES[i]: float(values[i]) for i in range(min(len(values), 17))}


# ================================================================
# Sidebar - Composition Inputs
# ================================================================
st.sidebar.title("🧪 Composition Input")

# Element inputs in compact groups
st.sidebar.markdown("**Alkali Metals**")
c1, c2, c3 = st.sidebar.columns(3)
with c1:
    li = st.number_input("Li %", 0.0, 100.0, 0.0, 0.1, key="elem_Li")
with c2:
    na = st.number_input("Na %", 0.0, 100.0, 0.0, 0.1, key="elem_Na")
with c3:
    k = st.number_input("K %", 0.0, 100.0, 0.0, 0.1, key="elem_K")

st.sidebar.markdown("**Alkaline Earth**")
c1, c2, c3, c4 = st.sidebar.columns(4)
with c1:
    mg = st.number_input("Mg %", 0.0, 100.0, 0.0, 0.1, key="elem_Mg")
with c2:
    ca = st.number_input("Ca %", 0.0, 100.0, 0.0, 0.1, key="elem_Ca")
with c3:
    sr = st.number_input("Sr %", 0.0, 100.0, 0.0, 0.1, key="elem_Sr")
with c4:
    ba = st.number_input("Ba %", 0.0, 100.0, 0.0, 0.1, key="elem_Ba")

st.sidebar.markdown("**Network Formers**")
c1, c2, c3 = st.sidebar.columns(3)
with c1:
    b = st.number_input("B %", 0.0, 100.0, 0.0, 0.1, key="elem_B")
with c2:
    al = st.number_input("Al %", 0.0, 100.0, 0.0, 0.1, key="elem_Al")
with c3:
    si = st.number_input("Si %", 0.0, 100.0, 0.0, 0.1, key="elem_Si")

st.sidebar.markdown("**Transition Metals / Others**")
c1, c2, c3, c4 = st.sidebar.columns(4)
with c1:
    ti = st.number_input("Ti %", 0.0, 100.0, 0.0, 0.1, key="elem_Ti")
with c2:
    fe = st.number_input("Fe %", 0.0, 100.0, 0.0, 0.1, key="elem_Fe")
with c3:
    zr = st.number_input("Zr %", 0.0, 100.0, 0.0, 0.1, key="elem_Zr")
with c4:
    pb = st.number_input("Pb %", 0.0, 100.0, 0.0, 0.1, key="elem_Pb")
c1, c2 = st.sidebar.columns(2)
with c1:
    p = st.number_input("P %", 0.0, 100.0, 0.0, 0.1, key="elem_P")
with c2:
    f_val = st.number_input("F %", 0.0, 100.0, 0.0, 0.1, key="elem_F")

st.sidebar.markdown("**Oxygen Mode**")
manual_o = st.sidebar.toggle(
    "Manual O Input", value=False, help="Auto-calc by charge neutrality when off"
)

# Manual O value stored separately to avoid widget conflict on correction
if "manual_o_val" not in st.session_state:
    st.session_state["manual_o_val"] = 0.0

if manual_o:
    user_o = st.sidebar.number_input(
        "O %",
        0.0,
        100.0,
        float(st.session_state["manual_o_val"]),
        0.1,
        key="manual_o_input",
    )
    st.session_state["manual_o_val"] = user_o
    raw_comp = [li, b, user_o, f_val, na, mg, al, si, p, k, ca, ti, fe, sr, zr, ba, pb]
    is_neutral, correct_o = check_neutrality(raw_comp)
    delta = abs(correct_o - user_o)
    if not is_neutral and delta > 0.01:
        st.sidebar.warning(
            f"Charge not neutral! Correct O = {correct_o:.2f} (diff {delta:.2f})"
        )
        if st.sidebar.button("✔️ Auto-Correct O", width="stretch"):
            st.session_state["manual_o_val"] = round(float(correct_o), 2)
            st.rerun()
    raw_comp_pred = [
        li,
        b,
        0.0,
        f_val,
        na,
        mg,
        al,
        si,
        p,
        k,
        ca,
        ti,
        fe,
        sr,
        zr,
        ba,
        pb,
    ]
    display_comp = raw_comp if (is_neutral and delta <= 0.01) else raw_comp_pred
else:
    st.sidebar.caption("O auto-calculated by charge neutrality")
    raw_comp = [li, b, 0.0, f_val, na, mg, al, si, p, k, ca, ti, fe, sr, zr, ba, pb]
    raw_comp_pred = raw_comp
    display_comp = raw_comp

# ================================================================
# Tabs
# ================================================================
tab1, tab2 = st.tabs(
    ["📊 Single-Point Prediction", "🧬 Multi-Objective GA Optimization"]
)

# ===== Tab 1: Single Prediction =====
with tab1:
    st.subheader("Single-Point Prediction")

    # Show real normalized composition (always visible)
    norm = normalize_composition(display_comp)
    oxides = to_oxide(norm)

    st.caption("Normalized Composition (mol%)")
    active_elems = [(e, norm[i]) for i, e in enumerate(ELEMENT_NAMES) if norm[i] > 0.01]
    if active_elems:
        elem_names = [e for e, _ in active_elems] + ["Total"]
        elem_vals = [f"{v:.2f}" for _, v in active_elems] + [f"{sum(norm):.1f}"]
        st.dataframe(
            pd.DataFrame([elem_vals], columns=elem_names),
            width="stretch",
            hide_index=True,
        )
        if oxides:
            ox_names = list(oxides.keys())
            ox_vals = [f"{v:.2f}" for v in oxides.values()]
            st.caption("Oxide Form (mol%)")
            st.dataframe(
                pd.DataFrame([ox_vals], columns=ox_names),
                width="stretch",
                hide_index=True,
            )
    else:
        st.info("Enter composition in sidebar")

    if st.button("🔮 Predict Properties", type="primary", width="stretch"):
        with st.spinner("Predicting (R model inference)..."):
            resp = predict_composition(raw_comp_pred)
        if "error" in resp:
            st.error(resp["error"])
        elif len(resp) < 5:
            st.warning("R server not ready, please retry")
        else:
            st.session_state["last_prediction"] = resp

            # 5 Property Cards
            cols = st.columns(5)
            for i, (prop, label) in enumerate(PROP_LABELS.items()):
                val = resp.get(prop, 0)
                with cols[i]:
                    if prop == "loss":
                        val_str = f"{val * 1000:.3f} ×10⁻³"
                    else:
                        val_str = f"{val:.3f} {PROP_UNITS[prop]}"
                    st.metric(label=f"{label}", value=val_str, border=True)

            # History
            if "history" not in st.session_state:
                st.session_state["history"] = []
            entry = dict(resp)
            entry.pop("_model_input", None)
            entry.pop("permittivity_sd", None)
            entry.pop("loss_sd", None)
            entry.pop("thermalC_sd", None)
            entry.pop("expansion_sd", None)
            entry.pop("modulus_sd", None)
            norm_vals = [resp.get(e, 0) for e in ELEMENT_NAMES]
            ox = to_oxide(norm_vals)
            entry.update({f"oxide_{k}": v for k, v in ox.items()})
            st.session_state["history"].append(entry)

    # History table
    if "history" in st.session_state and st.session_state["history"]:
        st.subheader("Prediction History")
        hist_df = pd.DataFrame(st.session_state["history"])
        # Show elements + properties; oxides are in the download
        show_cols = [c for c in ELEMENT_NAMES + PROP_KEYS if c in hist_df.columns]
        st.dataframe(hist_df[show_cols], width="stretch", hide_index=True)
        csv = hist_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 Download History CSV", csv, "mgea_history.csv", "text/csv"
        )

# ===== Tab 2: GA Optimization =====
with tab2:
    st.subheader("Multi-Objective GA Optimization")

    # Optimization targets
    with st.expander("🎯 Optimization Targets & Weights", expanded=True):
        st.caption("Set direction and weight for each property (0 = excluded)")
        cols = st.columns(5)
        ga_dir = {}
        ga_wt = {}
        for i, pk in enumerate(PROP_KEYS):
            with cols[i]:
                st.markdown(f"**{PROP_LABELS[pk]}**")
                ga_dir[pk] = st.selectbox(
                    "Direction",
                    ["↓ Minimize", "↑ Maximize"],
                    index=0 if PROP_DEFAULTS[pk] == "min" else 1,
                    key=f"ga_dir_{pk}",
                    label_visibility="collapsed",
                )
                ga_wt[pk] = st.number_input(
                    "Weight",
                    0.0,
                    10.0,
                    1.0,
                    0.5,
                    key=f"ga_wt_{pk}",
                    label_visibility="collapsed",
                )

    # GA Parameters
    with st.expander("⚙️ GA Parameters & Search Space", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            pop_size = st.number_input("Population Size", 5, 200, 30, 5)
        with c2:
            iters = st.number_input("Generations", 5, 100, 20, 5)
        with c3:
            mut = st.number_input("Mutation Rate", 0.01, 0.3, 0.05, 0.01)
        with c4:
            ga_boot = st.number_input("Bootstrap", 10, 1000, 100, 10)

        st.caption("Element search range (min ~ max, 0 = disabled)")
        ga_mins = {}
        ga_maxs = {}
        elist = [
            "Li",
            "Na",
            "K",
            "Mg",
            "Ca",
            "Sr",
            "Ba",
            "B",
            "Al",
            "Si",
            "P",
            "Ti",
            "Fe",
            "Zr",
            "Pb",
        ]

        # "Clear all" button
        if "clear_ga" not in st.session_state:
            st.session_state["clear_ga"] = 0
        if st.button("🗑️ Clear All", width="stretch"):
            st.session_state["clear_ga"] += 1
            st.rerun()

        ver = st.session_state["clear_ga"]
        for row_start in range(0, len(elist), 5):
            cols = st.columns(5)
            for j, e in enumerate(elist[row_start : row_start + 5]):
                with cols[j]:
                    st.markdown(f"**{e}**")
                    cmin, cmax = st.columns(2)
                    with cmin:
                        ga_mins[e] = st.number_input(
                            "min",
                            0.0,
                            100.0,
                            value=0.0,
                            step=1.0,
                            key=f"ga_min_{e}_v{ver}",
                            label_visibility="collapsed",
                        )
                    with cmax:
                        ga_maxs[e] = st.number_input(
                            "max",
                            0.0,
                            100.0,
                            value=100.0 if ver == 0 else 0.0,
                            step=1.0,
                            key=f"ga_max_{e}_v{ver}",
                            label_visibility="collapsed",
                        )

    if st.button(
        "🚀 Run Multi-Objective Optimization", type="primary", width="stretch"
    ):
        if all(v <= 0 for v in ga_maxs.values()):
            st.error("Enable at least one element (max > 0)")
        elif any(ga_mins[e] > ga_maxs[e] for e in elist):
            st.error("Some elements have min > max")
        else:
            with st.spinner("GA optimization running... please wait"):
                ga_params = {
                    "popSize": int(pop_size),
                    "iters": int(iters),
                    "mutationChance": float(mut),
                    "bootstrap_n": int(ga_boot),
                    "min_ratio": {e: float(ga_mins.get(e, 0.0)) for e in ELEMENT_NAMES},
                    "max_ratio": {
                        e: float(ga_maxs.get(e, 100.0)) if e in elist else 0.0
                        for e in ELEMENT_NAMES
                    },
                    "dir": {
                        pk: ("min" if "min" in ga_dir[pk] else "max")
                        for pk in PROP_KEYS
                    },
                    "wt": {pk: float(ga_wt.get(pk, 1.0)) for pk in PROP_KEYS},
                }
                ga_resp = run_ga_optimization(ga_params)

            if "error" in ga_resp:
                st.error(f"GA failed: {ga_resp['error']}")
                if "_r_output" in ga_resp:
                    with st.expander("R GA Output"):
                        st.code(ga_resp["_r_output"])
            elif "results" in ga_resp:
                results = ga_resp["results"]
                st.success("Optimization complete!")
                st.session_state["ga_results"] = results

    # Display GA results
    if "ga_results" in st.session_state and st.session_state["ga_results"]:
        results = st.session_state["ga_results"]
        df = pd.DataFrame(results)

        # Add oxide columns to each row
        oxide_cols = []
        for _, row in df.iterrows():
            norm_vals = [row.get(e, 0) for e in ELEMENT_NAMES]
            ox = to_oxide(norm_vals)
            oxide_cols.append(ox)
        df_ox = pd.DataFrame(oxide_cols)
        # Merge element cols (just the ones present), oxide cols, and property means
        elem_cols = [c for c in ELEMENT_NAMES if c in df.columns]
        mean_cols = [c for c in PROP_KEYS if c in df.columns]
        show_cols = elem_cols + list(df_ox.columns) + mean_cols
        if "Composite" in df.columns:
            show_cols.append("Composite")
        show_df = df[show_cols[:1]]  # just get structure
        # Build properly: take element cols from df, oxide from df_ox, means from df
        show_df = pd.DataFrame()
        for c in elem_cols:
            show_df[c] = df[c]
        for c in df_ox.columns:
            show_df[c] = df_ox[c]
        for c in mean_cols:
            show_df[c] = df[c]
        if "Composite" in df.columns:
            show_df["Composite"] = df["Composite"]

        top_n = st.number_input("Show Top N", 1, max(1, len(df)), min(20, len(df)), 5)

        # Download button
        csv = show_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 Download GA Results CSV",
            csv,
            "mgea_ga_results.csv",
            "text/csv",
            use_container_width=True,
            type="primary",
        )

        st.dataframe(show_df.head(top_n), width="stretch", hide_index=True)

        # Rank-normalized subplot per property
        st.subheader("Objective Space Distribution")
        plot_cols = [c for c in PROP_KEYS if c in df.columns]
        if plot_cols:
            from plotly.subplots import make_subplots

            n = min(50, len(df))
            top_n_df = df.head(n)

            fig = make_subplots(
                rows=len(plot_cols),
                cols=1,
                subplot_titles=[PROP_LABELS[c] for c in plot_cols],
                shared_xaxes=True,
                vertical_spacing=0.05,
            )

            for i, c in enumerate(plot_cols):
                y_vals = top_n_df[c].values
                y_min, y_max = y_vals.min(), y_vals.max()
                if y_max > y_min:
                    y_norm = (y_vals - y_min) / (y_max - y_min)
                else:
                    y_norm = y_vals - y_min
                x_vals = list(range(1, n + 1))

                fig.add_trace(
                    go.Bar(
                        x=x_vals,
                        y=y_norm,
                        marker_color="#bdc3c7",
                        name=f"{PROP_LABELS[c]} Bar",
                        showlegend=False,
                        hovertemplate=f"{PROP_LABELS[c]}: %{{customdata:.3f}}<extra></extra>",
                        customdata=y_vals,
                    ),
                    row=i + 1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=x_vals,
                        y=y_norm,
                        mode="lines+markers",
                        marker=dict(size=6, color="#e74c3c"),
                        line=dict(color="#e74c3c"),
                        name=f"{PROP_LABELS[c]} Line",
                        showlegend=False,
                        hovertemplate=f"{PROP_LABELS[c]}: %{{customdata:.3f}}<extra></extra>",
                        customdata=y_vals,
                    ),
                    row=i + 1,
                    col=1,
                )
                fig.add_annotation(
                    x=1,
                    y=0,
                    xref=f"x{i + 1}",
                    yref=f"y{i + 1}",
                    text=f"min:{y_min:.3f}  max:{y_max:.3f}",
                    showarrow=False,
                    font=dict(size=9, color="#888"),
                    xanchor="right",
                    yanchor="bottom",
                )

            fig.update_layout(
                height=220 * len(plot_cols),
                showlegend=False,
                margin=dict(l=40, r=20, t=40, b=20),
            )
            fig.update_xaxes(
                tickvals=list(range(1, n + 1, max(1, n // 5))),
                row=len(plot_cols),
                col=1,
            )
            fig.update_xaxes(title_text="Rank", row=len(plot_cols), col=1)
            st.plotly_chart(fig, width="stretch")

        # Best candidates table
        st.subheader("Best CandidatesDetail")
        dir_ga = {pk: ("min" if "min" in ga_dir[pk] else "max") for pk in PROP_KEYS}
        best_rows = []

        def fmt_val(pk, v):
            if pk == "loss":
                return f"{v * 1000:.3f}×10⁻³"
            return f"{v:.3f}"

        # Composite best
        if "Composite" in df.columns:
            idx = df["Composite"].idxmax()
            row = {"Category": f"🏆 Overall Best (No.{idx + 1})"}
            row.update(
                {PROP_LABELS[pk]: fmt_val(pk, df.loc[idx, pk]) for pk in PROP_KEYS}
            )
            ox_str = ", ".join(
                [f"{c} {show_df.loc[idx, c]:.2f}" for c in df_ox.columns]
            )
            row["Oxide Composition"] = ox_str
            best_rows.append(row)
        # Per-property best
        for pk in PROP_KEYS:
            idx = df[pk].idxmin() if dir_ga[pk] == "min" else df[pk].idxmax()
            row = {
                "Category": f"{PROP_LABELS[pk]} {'↓' if dir_ga[pk] == 'min' else '↑'} Best (No.{idx + 1})"
            }
            row.update(
                {PROP_LABELS[pk2]: fmt_val(pk2, df.loc[idx, pk2]) for pk2 in PROP_KEYS}
            )
            ox_str = ", ".join(
                [f"{c} {show_df.loc[idx, c]:.2f}" for c in df_ox.columns]
            )
            row["Oxide Composition"] = ox_str
            best_rows.append(row)
        st.dataframe(pd.DataFrame(best_rows), width="stretch", hide_index=True)
# ================================================================
# Footer
# ================================================================
st.divider()
st.markdown(
    "<div style='text-align:center; color:#888; font-size:0.85em;'>"
    "<b>Jincheng Qin</b><br>"
    "Multiobjective optimization of dielectric, thermal, and mechanical properties "
    "of inorganic glasses utilizing explainable machine learning and genetic algorithm<br>"
    "<i>Materials Genome Engineering Advances</i> 2025 &nbsp; "
    "<a href='https://doi.org/10.1002/mgea.70005' target='_blank'>DOI: 10.1002/mgea.70005</a>"
    "</div>",
    unsafe_allow_html=True,
)


from pathlib import Path
import subprocess

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "project.sh"
RAW_DIR = ROOT / "results" / "raw"
REPORT_DIR = ROOT / "results" / "reports"

st.set_page_config(
    page_title="Energy Kubernetes",
    page_icon="🌱",
    layout="wide",
)

st.title("🌱 Energy-Aware Kubernetes")
st.caption("AI workload monitoring and energy experiment dashboard")

st.sidebar.header("Navigation")
page = st.sidebar.radio(
    "Select page",
    ["Overview", "Experiments", "Results", "Scheduler"],
)

def run_project_command(command):
    """Run an existing project.sh command."""
    if not PROJECT.exists():
        st.error("project.sh was not found.")
        return

    try:
        result = subprocess.run(
            ["bash", str(PROJECT), command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=900,
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        st.session_state["last_output"] = output or "Command completed."

        if result.returncode == 0:
            st.success(f"Command '{command}' completed.")
        else:
            st.error(
                f"Command '{command}' failed "
                f"(exit code {result.returncode})."
            )

    except subprocess.TimeoutExpired:
        st.error("Command timed out. Check the terminal and cluster status.")
    except OSError as exc:
        st.error(f"Could not execute command: {exc}")


def load_csv_results():
    """Load CSV files without modifying the original results."""
    if not RAW_DIR.exists():
        return pd.DataFrame()

    frames = []

    for path in sorted(RAW_DIR.glob("*.csv")):
        try:
            frame = pd.read_csv(path)
            frame["source_file"] = path.name
            frames.append(frame)
        except (OSError, pd.errors.ParserError):
            continue

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True, sort=False)


def find_column(df, keywords):
    """Find a likely matching column by name."""
    for column in df.columns:
        normalized = str(column).lower().replace(" ", "_")
        if any(word in normalized for word in keywords):
            return column
    return None


if page == "Overview":
    st.subheader("System overview")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Check cluster status", use_container_width=True):
            run_project_command("status")

    with col2:
        if st.button("Start Minikube", use_container_width=True):
            run_project_command("start")

    with col3:
        if st.button("Refresh data", use_container_width=True):
            st.rerun()

    st.divider()

    df = load_csv_results()

    if df.empty:
        st.info(
            "No raw CSV results found yet. Run an experiment "
            "to populate the dashboard."
        )
    else:
        st.metric("CSV rows loaded", len(df))
        st.metric(
            "Result files",
            df["source_file"].nunique(),
        )
        st.caption(
            "These figures describe saved experiment records, "
            "not live Kubernetes metrics."
        )

        st.subheader("Recent measurement records")
        st.dataframe(df.tail(20), use_container_width=True)

    if st.button("Inspect cluster and pods"):
        try:
            result = subprocess.run(
                ["kubectl", "get", "nodes,pods", "-A"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            st.code(result.stdout or result.stderr)
        except (OSError, subprocess.TimeoutExpired) as exc:
            st.error(str(exc))


elif page == "Experiments":
    st.subheader("Run energy experiments")

    st.warning(
        "These controls execute real project scripts and can change "
        "the running Kubernetes workload."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Baseline")
        st.write("Temporarily scale the CPU workload to zero and measure.")
        if st.button("Run baseline", use_container_width=True):
            run_project_command("baseline")

    with col2:
        st.markdown("### Loaded workload")
        st.write("Run the CPU workload and estimate machine-level energy.")
        if st.button("Run load test", use_container_width=True):
            run_project_command("load-test")

    if st.button("Generate report", use_container_width=True):
        run_project_command("report")

    if "last_output" in st.session_state:
        st.subheader("Command output")
        st.code(st.session_state["last_output"])


elif page == "Results":
    st.subheader("Experiment results")

    df = load_csv_results()

    if df.empty:
        st.info("No CSV results are available in results/raw/.")
    else:
        st.write("Available measurement data")
        st.dataframe(df, use_container_width=True)

        numeric_columns = df.select_dtypes(
            include="number"
        ).columns.tolist()

        value_column = find_column(
            df,
            ["energy", "emissions", "cpu", "memory"],
        )

        if value_column not in numeric_columns:
            value_column = None

        if numeric_columns:
            selected_column = st.selectbox(
                "Metric to visualize",
                numeric_columns,
                index=(
                    numeric_columns.index(value_column)
                    if value_column else 0
                ),
            )

            chart_data = df[[selected_column]].copy()
            chart_data["record"] = range(1, len(chart_data) + 1)

            fig = px.line(
                chart_data,
                x="record",
                y=selected_column,
                title=f"{selected_column} across records",
                markers=True,
            )
            st.plotly_chart(fig, use_container_width=True)

        st.download_button(
            "Download combined CSV",
            data=df.to_csv(index=False),
            file_name="energy_experiment_results.csv",
            mime="text/csv",
        )

    st.subheader("Generated reports")

    if REPORT_DIR.exists():
        reports = sorted(REPORT_DIR.glob("*.md"))
        if not reports:
            st.caption("No Markdown reports found yet.")

        for report in reports:
            with st.expander(report.name):
                st.markdown(
                    report.read_text(encoding="utf-8")
                )


elif page == "Scheduler":
    st.subheader("Energy-aware scheduling")
    st.info(
        "Future research component: the scheduling algorithm "
        "has not yet been implemented."
    )

    st.markdown(
        """
        **Planned capabilities**

        - Collect workload and node resource metrics.
        - Evaluate scheduling and optimization policies.
        - Compare baseline scheduling with energy-aware scheduling.
        - Measure energy estimates and workload performance.
        - Generate comparative experiment reports.
        """
    )

    st.metric("Scheduling policy", "Not implemented")
    st.metric("Policy comparison", "Not available")

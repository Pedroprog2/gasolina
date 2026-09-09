
import io
import os
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "ftir_database.db"
SPECTRA_DIR = APP_DIR / "spectra"
SPECTRA_DIR.mkdir(exist_ok=True)

st.set_page_config(
    page_title="Banco Espectral ATR-FTIR",
    page_icon="🧪",
    layout="wide",
)

# ---------- Banco de dados ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spectra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT NOT NULL,
            acquisition_id TEXT NOT NULL UNIQUE,
            fuel_type TEXT NOT NULL,
            municipality TEXT,
            collection_date TEXT,
            acquisition_date TEXT,
            instrument TEXT,
            atr_accessory TEXT,
            resolution_cm1 REAL,
            scans INTEGER,
            replicate INTEGER,
            methanol_ref REAL,
            reference_method TEXT,
            conformity TEXT,
            filename TEXT,
            filepath TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn

def save_record(record):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO spectra (
                sample_id, acquisition_id, fuel_type, municipality,
                collection_date, acquisition_date, instrument, atr_accessory,
                resolution_cm1, scans, replicate, methanol_ref,
                reference_method, conformity, filename, filepath, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["sample_id"],
            record["acquisition_id"],
            record["fuel_type"],
            record["municipality"],
            record["collection_date"],
            record["acquisition_date"],
            record["instrument"],
            record["atr_accessory"],
            record["resolution_cm1"],
            record["scans"],
            record["replicate"],
            record["methanol_ref"],
            record["reference_method"],
            record["conformity"],
            record["filename"],
            record["filepath"],
            record["notes"],
        ))
        conn.commit()
    finally:
        conn.close()

def load_records():
    conn = get_conn()
    try:
        return pd.read_sql_query(
            "SELECT * FROM spectra ORDER BY created_at DESC, id DESC",
            conn
        )
    finally:
        conn.close()

# ---------- Leitura do espectro ----------
def parse_spectrum(uploaded_file):
    raw = uploaded_file.getvalue()

    attempts = [
        dict(sep=None, engine="python"),
        dict(sep=";"),
        dict(sep=","),
        dict(sep="\t"),
        dict(delim_whitespace=True),
    ]

    last_error = None

    for kwargs in attempts:
        try:
            df = pd.read_csv(io.BytesIO(raw), **kwargs)
            if df.shape[1] >= 2:
                break
        except Exception as e:
            last_error = e
            df = None
    else:
        raise ValueError(f"Não foi possível interpretar o arquivo. {last_error}")

    # Mantém apenas as duas primeiras colunas
    df = df.iloc[:, :2].copy()
    df.columns = ["wavenumber", "intensity"]

    # Conversão robusta
    for col in ["wavenumber", "intensity"]:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(",", ".", regex=False)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna()

    if len(df) < 5:
        raise ValueError(
            "O arquivo precisa conter pelo menos 5 linhas válidas com "
            "número de onda e intensidade."
        )

    df = df.sort_values("wavenumber", ascending=False).reset_index(drop=True)
    return df

# ---------- Interface ----------
st.title("Banco Espectral ATR-FTIR")
st.caption(
    "Protótipo para cadastro, visualização e organização de espectros "
    "de combustíveis."
)

tab1, tab2, tab3 = st.tabs(
    ["📥 Registrar espectro", "🔎 Consultar banco", "📊 Visualizar registro"]
)

with tab1:
    st.subheader("Nova aquisição espectral")

    uploaded = st.file_uploader(
        "Carregue um espectro em CSV ou TXT",
        type=["csv", "txt"],
        help=(
            "O arquivo deve conter duas colunas: número de onda (cm⁻¹) "
            "e intensidade/absorbância."
        ),
    )

    spectrum_df = None
    if uploaded is not None:
        try:
            spectrum_df = parse_spectrum(uploaded)
            st.success(f"Arquivo lido com sucesso: {len(spectrum_df)} pontos.")

            fig = px.line(
                spectrum_df,
                x="wavenumber",
                y="intensity",
                labels={
                    "wavenumber": "Número de onda (cm⁻¹)",
                    "intensity": "Intensidade / absorbância",
                },
            )
            fig.update_layout(height=420)
            fig.update_xaxes(autorange="reversed")
            st.plotly_chart(fig, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            c1.metric(
                "Faixa espectral",
                f"{spectrum_df['wavenumber'].max():.0f}–"
                f"{spectrum_df['wavenumber'].min():.0f} cm⁻¹",
            )
            c2.metric("Pontos", f"{len(spectrum_df)}")
            c3.metric("Arquivo", uploaded.name)

        except Exception as e:
            st.error(str(e))

    st.markdown("---")
    st.subheader("Metadados")

    with st.form("metadata_form"):
        c1, c2, c3 = st.columns(3)

        with c1:
            sample_id = st.text_input(
                "ID da amostra",
                value="ETOH_0001",
                help="Identificador permanente da amostra física.",
            )
            fuel_type = st.selectbox(
                "Combustível",
                ["Etanol hidratado", "Gasolina"],
            )
            municipality = st.text_input(
                "Município / origem",
                value="São Luís - MA",
            )
            collection_date = st.date_input(
                "Data de coleta",
                value=date.today(),
            )

        with c2:
            replicate = st.number_input(
                "Replicata",
                min_value=1,
                max_value=20,
                value=1,
                step=1,
            )
            acquisition_date = st.date_input(
                "Data de aquisição",
                value=date.today(),
            )
            resolution = st.selectbox(
                "Resolução espectral (cm⁻¹)",
                [0.5, 1.0, 2.0, 4.0, 8.0, 16.0],
                index=3,
            )
            scans = st.selectbox(
                "Número de varreduras",
                [16, 32, 64, 100],
                index=1,
            )

        with c3:
            instrument = st.text_input(
                "Instrumento",
                value="Shimadzu IRPrestige-21",
            )
            atr_accessory = st.text_input(
                "Acessório ATR",
                value="A confirmar",
            )
            methanol_ref = st.number_input(
                "Metanol por método de referência (% v/v)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.2f",
            )
            reference_method = st.selectbox(
                "Método de referência",
                ["CG-FID", "Outro", "Não disponível"],
            )

        conformity = st.selectbox(
            "Classificação de conformidade",
            ["Conforme", "Não conforme", "Não avaliada"],
            index=2,
        )
        notes = st.text_area("Observações")

        acquisition_id = (
            f"{sample_id.strip()}_R{int(replicate):02d}"
            if sample_id.strip()
            else ""
        )

        st.caption(
            f"ID de aquisição previsto: **{acquisition_id or '—'}**"
        )

        submitted = st.form_submit_button(
            "Registrar amostra e espectro",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if uploaded is None or spectrum_df is None:
            st.error("Carregue um espectro válido antes de registrar.")
        elif not sample_id.strip():
            st.error("Informe o ID da amostra.")
        else:
            safe_name = f"{acquisition_id}_{Path(uploaded.name).name}"
            dest = SPECTRA_DIR / safe_name

            if dest.exists():
                st.error(
                    "Já existe um arquivo para esse ID de aquisição. "
                    "Altere a replicata ou o ID da amostra."
                )
            else:
                dest.write_bytes(uploaded.getvalue())

                record = {
                    "sample_id": sample_id.strip(),
                    "acquisition_id": acquisition_id,
                    "fuel_type": fuel_type,
                    "municipality": municipality.strip(),
                    "collection_date": collection_date.isoformat(),
                    "acquisition_date": acquisition_date.isoformat(),
                    "instrument": instrument.strip(),
                    "atr_accessory": atr_accessory.strip(),
                    "resolution_cm1": float(resolution),
                    "scans": int(scans),
                    "replicate": int(replicate),
                    "methanol_ref": float(methanol_ref),
                    "reference_method": reference_method,
                    "conformity": conformity,
                    "filename": uploaded.name,
                    "filepath": str(dest.relative_to(APP_DIR)),
                    "notes": notes.strip(),
                }

                try:
                    save_record(record)
                    st.success(
                        f"Registro {acquisition_id} salvo com sucesso."
                    )
                except sqlite3.IntegrityError:
                    if dest.exists():
                        dest.unlink()
                    st.error(
                        "Esse ID de aquisição já está registrado no banco."
                    )

with tab2:
    st.subheader("Consulta ao banco espectral")

    records = load_records()

    if records.empty:
        st.info("Ainda não há registros no banco.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            filter_fuel = st.multiselect(
                "Filtrar por combustível",
                sorted(records["fuel_type"].dropna().unique()),
            )
        with c2:
            filter_status = st.multiselect(
                "Filtrar por conformidade",
                sorted(records["conformity"].dropna().unique()),
            )

        filtered = records.copy()

        if filter_fuel:
            filtered = filtered[
                filtered["fuel_type"].isin(filter_fuel)
            ]
        if filter_status:
            filtered = filtered[
                filtered["conformity"].isin(filter_status)
            ]

        cols_show = [
            "acquisition_id",
            "sample_id",
            "fuel_type",
            "municipality",
            "resolution_cm1",
            "scans",
            "methanol_ref",
            "reference_method",
            "conformity",
            "filename",
            "created_at",
        ]

        st.dataframe(
            filtered[cols_show],
            use_container_width=True,
            hide_index=True,
        )

        csv_bytes = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Baixar metadados filtrados (.csv)",
            data=csv_bytes,
            file_name="metadata_ftir.csv",
            mime="text/csv",
        )

with tab3:
    st.subheader("Visualização de um registro")

    records = load_records()

    if records.empty:
        st.info("Registre pelo menos um espectro para utilizar esta área.")
    else:
        chosen = st.selectbox(
            "Selecione a aquisição",
            records["acquisition_id"].tolist(),
        )

        row = records.loc[
            records["acquisition_id"] == chosen
        ].iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Amostra", row["sample_id"])
        c2.metric("Combustível", row["fuel_type"])
        c3.metric("Resolução", f"{row['resolution_cm1']} cm⁻¹")
        c4.metric("Varreduras", str(row["scans"]))

        st.write(
            {
                "Origem": row["municipality"],
                "Método de referência": row["reference_method"],
                "Metanol (% v/v)": row["methanol_ref"],
                "Conformidade": row["conformity"],
                "Acessório ATR": row["atr_accessory"],
                "Arquivo original": row["filename"],
            }
        )

        file_path = APP_DIR / row["filepath"]

        if file_path.exists():
            try:
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                tmp = io.BytesIO(file_bytes)
                tmp.name = row["filename"]
                df_plot = parse_spectrum(tmp)

                fig = px.line(
                    df_plot,
                    x="wavenumber",
                    y="intensity",
                    labels={
                        "wavenumber": "Número de onda (cm⁻¹)",
                        "intensity": "Intensidade / absorbância",
                    },
                    title=chosen,
                )
                fig.update_xaxes(autorange="reversed")
                fig.update_layout(height=450)
                st.plotly_chart(fig, use_container_width=True)

                st.download_button(
                    "Baixar espectro original",
                    data=file_bytes,
                    file_name=row["filename"],
                    mime="text/plain",
                )
            except Exception as e:
                st.error(f"Erro ao abrir o espectro: {e}")
        else:
            st.warning("O arquivo espectral associado não foi encontrado.")

st.markdown("---")
st.caption(
    "Protótipo de pesquisa — Banco Espectral ATR-FTIR | "
    "Python + Streamlit + SQLite"
)


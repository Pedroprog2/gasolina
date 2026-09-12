import io
import hmac
import mimetypes
import re
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Banco Espectral ATR-FTIR", page_icon="🧪", layout="wide")
BUCKET = "ftir-spectra"

def require_app_password():
    expected = st.secrets.get("APP_PASSWORD", "")
    if not expected:
        return
    supplied = st.text_input("Senha de acesso", type="password")
    if not supplied:
        st.info("Informe a senha para acessar a plataforma.")
        st.stop()
    if not hmac.compare_digest(str(supplied), str(expected)):
        st.error("Senha incorreta.")
        st.stop()

@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"]

    # Preferência atual: Secret key do Supabase (sb_secret_...).
    # Mantém compatibilidade com a antiga service_role key.
    key = st.secrets.get("SUPABASE_SECRET_KEY", "")
    if not key:
        key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not key:
        raise RuntimeError(
            "Nenhuma chave de backend do Supabase foi encontrada nos Secrets. "
            "Defina SUPABASE_SECRET_KEY."
        )

    return create_client(url, key)

require_app_password()

try:
    supabase = get_supabase()
except Exception as e:
    st.error("Não foi possível conectar ao Supabase. Confira os Secrets do Streamlit.")
    st.exception(e)
    st.stop()

def safe_component(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("._") or "arquivo"

def parse_spectrum_bytes(raw: bytes, filename: str = "spectrum.csv") -> pd.DataFrame:
    attempts = [
        dict(sep=None, engine="python"),
        dict(sep=";"),
        dict(sep=","),
        dict(sep="\t"),
        dict(sep=r"\s+", engine="python"),
    ]
    df = None
    last_error = None

    for kwargs in attempts:
        try:
            candidate = pd.read_csv(io.BytesIO(raw), **kwargs)
            if candidate.shape[1] >= 2:
                df = candidate
                break
        except Exception as exc:
            last_error = exc

    if df is None:
        for kwargs in attempts:
            try:
                candidate = pd.read_csv(io.BytesIO(raw), header=None, **kwargs)
                if candidate.shape[1] >= 2:
                    df = candidate
                    break
            except Exception as exc:
                last_error = exc

    if df is None:
        raise ValueError(f"Não foi possível interpretar {filename}. Erro final: {last_error}")

    df = df.iloc[:, :2].copy()
    df.columns = ["wavenumber", "intensity"]

    for col in ["wavenumber", "intensity"]:
        df[col] = df[col].astype(str).str.strip().str.replace(",", ".", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna()
    if len(df) < 5:
        raise ValueError("O arquivo precisa conter pelo menos cinco pares numéricos.")

    return df.sort_values("wavenumber", ascending=False).reset_index(drop=True)

def upload_spectrum(storage_path: str, file_bytes: bytes, filename: str):
    content_type = mimetypes.guess_type(filename)[0] or "text/plain"
    return (
        supabase.storage.from_(BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "false"},
        )
    )

def remove_spectrum_if_needed(storage_path: str):
    try:
        supabase.storage.from_(BUCKET).remove([storage_path])
    except Exception:
        pass

def insert_metadata(record: dict):
    return supabase.table("spectra").insert(record).execute()

def get_records() -> pd.DataFrame:
    response = supabase.table("spectra").select("*").order("created_at", desc=True).execute()
    return pd.DataFrame(response.data or [])

def download_spectrum(storage_path: str) -> bytes:
    return supabase.storage.from_(BUCKET).download(storage_path)

def spectrum_plot(df, title=None):
    fig = px.line(
        df, x="wavenumber", y="intensity",
        labels={"wavenumber": "Número de onda (cm⁻¹)", "intensity": "Intensidade / absorbância"},
        title=title
    )
    fig.update_xaxes(autorange="reversed")
    fig.update_layout(height=450)
    return fig

st.title("Banco Espectral ATR-FTIR")
st.caption("Protótipo com armazenamento persistente: Streamlit + Supabase PostgreSQL + Supabase Storage.")

tab1, tab2, tab3 = st.tabs(["📥 Registrar espectro", "🔎 Consultar banco", "📊 Visualizar registro"])

with tab1:
    st.subheader("Nova aquisição espectral")
    uploaded = st.file_uploader(
        "Carregue o espectro",
        type=["csv", "txt"],
        help="Duas colunas: número de onda (cm⁻¹) e intensidade/absorbância."
    )

    spectrum_df = None
    uploaded_bytes = None

    if uploaded is not None:
        uploaded_bytes = uploaded.getvalue()
        try:
            spectrum_df = parse_spectrum_bytes(uploaded_bytes, uploaded.name)
            st.success(f"Arquivo lido com sucesso: {len(spectrum_df)} pontos.")
            st.plotly_chart(spectrum_plot(spectrum_df), use_container_width=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("Faixa espectral", f"{spectrum_df['wavenumber'].max():.0f}–{spectrum_df['wavenumber'].min():.0f} cm⁻¹")
            c2.metric("Pontos", str(len(spectrum_df)))
            c3.metric("Arquivo", uploaded.name)
        except Exception as exc:
            st.error(str(exc))

    st.divider()
    st.subheader("Metadados")

    with st.form("metadata_form"):
        c1, c2, c3 = st.columns(3)

        with c1:
            sample_id = st.text_input("ID da amostra", value="ETOH_0001")
            fuel_type = st.selectbox("Combustível", ["Etanol hidratado", "Gasolina"])
            municipality = st.text_input("Município / origem", value="São Luís - MA")
            collection_date = st.date_input("Data de coleta", value=date.today())

        with c2:
            replicate = st.number_input("Replicata", min_value=1, max_value=50, value=1, step=1)
            acquisition_date = st.date_input("Data de aquisição", value=date.today())
            resolution = st.selectbox("Resolução espectral (cm⁻¹)", [0.5, 1.0, 2.0, 4.0, 8.0, 16.0], index=3)
            scans = st.selectbox("Número de varreduras", [16, 32, 64, 100], index=1)

        with c3:
            instrument = st.text_input("Instrumento", value="Shimadzu IRPrestige-21")
            atr_accessory = st.text_input("Acessório ATR", value="A confirmar")
            methanol_ref = st.number_input("Metanol por método de referência (% v/v)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
            reference_method = st.selectbox("Método de referência", ["CG-FID", "Outro", "Não disponível"])

        conformity = st.selectbox("Classificação de conformidade", ["Conforme", "Não conforme", "Não avaliada"], index=2)
        notes = st.text_area("Observações")

        acquisition_id = f"{safe_component(sample_id)}_R{int(replicate):02d}" if sample_id.strip() else ""
        st.caption(f"ID de aquisição previsto: **{acquisition_id or '—'}**")

        submitted = st.form_submit_button("Registrar amostra e espectro", type="primary", use_container_width=True)

    if submitted:
        if uploaded is None or uploaded_bytes is None or spectrum_df is None:
            st.error("Carregue um espectro válido antes de registrar.")
        elif not sample_id.strip():
            st.error("Informe o ID da amostra.")
        else:
            original_name = safe_component(Path(uploaded.name).name)
            fuel_folder = "etanol" if fuel_type == "Etanol hidratado" else "gasolina"
            storage_path = f"{fuel_folder}/{safe_component(sample_id)}/{acquisition_id}_{original_name}"

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
                "original_filename": uploaded.name,
                "storage_path": storage_path,
                "spectral_points": int(len(spectrum_df)),
                "wavenumber_max": float(spectrum_df["wavenumber"].max()),
                "wavenumber_min": float(spectrum_df["wavenumber"].min()),
                "notes": notes.strip(),
            }

            try:
                upload_spectrum(storage_path, uploaded_bytes, uploaded.name)
                try:
                    insert_metadata(record)
                except Exception:
                    remove_spectrum_if_needed(storage_path)
                    raise
                st.success(f"{acquisition_id} registrado permanentemente no Supabase.")
                st.info(f"Arquivo armazenado em: {BUCKET}/{storage_path}")
            except Exception as exc:
                st.error("Não foi possível concluir o registro.")
                st.exception(exc)

with tab2:
    st.subheader("Consulta ao banco espectral")
    try:
        records = get_records()
    except Exception as exc:
        st.error("Erro ao consultar o Supabase.")
        st.exception(exc)
        records = pd.DataFrame()

    if records.empty:
        st.info("Ainda não há registros no banco.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            filter_fuel = st.multiselect("Combustível", sorted(records["fuel_type"].dropna().unique()))
        with c2:
            filter_status = st.multiselect("Conformidade", sorted(records["conformity"].dropna().unique()))
        with c3:
            search_id = st.text_input("Buscar ID", placeholder="Ex.: ETOH_0028")

        filtered = records.copy()
        if filter_fuel:
            filtered = filtered[filtered["fuel_type"].isin(filter_fuel)]
        if filter_status:
            filtered = filtered[filtered["conformity"].isin(filter_status)]
        if search_id.strip():
            mask = (
                filtered["sample_id"].astype(str).str.contains(search_id.strip(), case=False, na=False)
                | filtered["acquisition_id"].astype(str).str.contains(search_id.strip(), case=False, na=False)
            )
            filtered = filtered[mask]

        cols_show = [
            "acquisition_id", "sample_id", "fuel_type", "municipality",
            "resolution_cm1", "scans", "methanol_ref", "reference_method",
            "conformity", "spectral_points", "created_at"
        ]
        existing_cols = [c for c in cols_show if c in filtered.columns]
        st.dataframe(filtered[existing_cols], use_container_width=True, hide_index=True)

        st.download_button(
            "Baixar metadados filtrados (.csv)",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name="metadata_ftir.csv",
            mime="text/csv"
        )

with tab3:
    st.subheader("Visualização de um registro")
    try:
        records = get_records()
    except Exception as exc:
        st.error("Erro ao consultar o Supabase.")
        st.exception(exc)
        records = pd.DataFrame()

    if records.empty:
        st.info("Registre pelo menos um espectro para utilizar esta área.")
    else:
        chosen = st.selectbox("Selecione a aquisição", records["acquisition_id"].tolist())
        row = records.loc[records["acquisition_id"] == chosen].iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Amostra", str(row["sample_id"]))
        c2.metric("Combustível", str(row["fuel_type"]))
        c3.metric("Resolução", f"{row['resolution_cm1']} cm⁻¹")
        c4.metric("Varreduras", str(row["scans"]))

        st.json({
            "Origem": row.get("municipality"),
            "Data de coleta": row.get("collection_date"),
            "Data de aquisição": row.get("acquisition_date"),
            "Método de referência": row.get("reference_method"),
            "Metanol (% v/v)": row.get("methanol_ref"),
            "Conformidade": row.get("conformity"),
            "Instrumento": row.get("instrument"),
            "Acessório ATR": row.get("atr_accessory"),
            "Arquivo original": row.get("original_filename"),
            "Caminho no Storage": row.get("storage_path"),
        })

        try:
            file_bytes = download_spectrum(row["storage_path"])
            df_plot = parse_spectrum_bytes(file_bytes, row.get("original_filename", "spectrum.csv"))
            st.plotly_chart(spectrum_plot(df_plot, chosen), use_container_width=True)
            st.download_button(
                "Baixar espectro original",
                data=file_bytes,
                file_name=row.get("original_filename", f"{chosen}.csv"),
                mime="application/octet-stream"
            )
        except Exception as exc:
            st.error("O registro existe, mas não foi possível recuperar o arquivo no Supabase Storage.")
            st.exception(exc)

st.divider()
st.caption("Protótipo de pesquisa — Banco Espectral ATR-FTIR | Python + Streamlit + Supabase")

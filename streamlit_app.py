
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

st.set_page_config(
    page_title="Banco Espectral ATR-FTIR",
    page_icon="🧪",
    layout="wide",
)

BUCKET = "ftir-spectra"

# ============================================================
# Configuração / segurança
# ============================================================
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

    key = st.secrets.get("SUPABASE_SECRET_KEY", "")
    if not key:
        key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not key:
        raise RuntimeError(
            "Nenhuma chave de backend do Supabase foi encontrada. "
            "Defina SUPABASE_SECRET_KEY nos Secrets do Streamlit."
        )

    return create_client(url, key)


require_app_password()

try:
    supabase = get_supabase()
except Exception as exc:
    st.error("Não foi possível conectar ao Supabase.")
    st.exception(exc)
    st.stop()


# ============================================================
# Utilidades
# ============================================================
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

    for header in ["infer", None]:
        for kwargs in attempts:
            try:
                candidate = pd.read_csv(
                    io.BytesIO(raw),
                    header=header,
                    **kwargs
                )
                if candidate.shape[1] >= 2:
                    df = candidate
                    break
            except Exception as exc:
                last_error = exc
        if df is not None:
            break

    if df is None:
        raise ValueError(
            f"Não foi possível interpretar {filename}. Erro final: {last_error}"
        )

    df = df.iloc[:, :2].copy()
    df.columns = ["wavenumber", "intensity"]

    for col in ["wavenumber", "intensity"]:
        df[col] = (
            df[col]
            .astype(str)
            .str.strip()
            .str.replace(",", ".", regex=False)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna()

    if len(df) < 5:
        raise ValueError(
            "O arquivo precisa conter pelo menos cinco pares numéricos."
        )

    return (
        df.sort_values("wavenumber", ascending=False)
        .reset_index(drop=True)
    )


def spectrum_plot(df: pd.DataFrame, title: str | None = None):
    fig = px.line(
        df,
        x="wavenumber",
        y="intensity",
        labels={
            "wavenumber": "Número de onda (cm⁻¹)",
            "intensity": "Intensidade / absorbância",
        },
        title=title,
    )
    fig.update_xaxes(autorange="reversed")
    fig.update_layout(height=450)
    return fig


def query_table(table: str, order_col: str | None = None) -> pd.DataFrame:
    q = supabase.table(table).select("*")
    if order_col:
        q = q.order(order_col, desc=True)
    resp = q.execute()
    return pd.DataFrame(resp.data or [])


def get_samples() -> pd.DataFrame:
    resp = (
        supabase.table("samples")
        .select("*")
        .order("sample_id")
        .execute()
    )
    return pd.DataFrame(resp.data or [])


def sample_exists(sample_id: str) -> bool:
    resp = (
        supabase.table("samples")
        .select("sample_id")
        .eq("sample_id", sample_id)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def acquisition_exists(acquisition_id: str) -> bool:
    resp = (
        supabase.table("spectral_acquisitions")
        .select("acquisition_id")
        .eq("acquisition_id", acquisition_id)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def upload_spectrum(storage_path: str, file_bytes: bytes, filename: str):
    content_type = mimetypes.guess_type(filename)[0] or "text/plain"
    return (
        supabase.storage
        .from_(BUCKET)
        .upload(
            path=storage_path,
            file=file_bytes,
            file_options={
                "content-type": content_type,
                "upsert": "false",
            },
        )
    )


def remove_spectrum_if_needed(storage_path: str):
    try:
        supabase.storage.from_(BUCKET).remove([storage_path])
    except Exception:
        pass


def download_spectrum(storage_path: str) -> bytes:
    return supabase.storage.from_(BUCKET).download(storage_path)


def nullable_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


# ============================================================
# Interface
# ============================================================
st.title("Banco Espectral ATR-FTIR")
st.caption(
    "Arquitetura relacional: amostras, aquisições espectrais "
    "e análises de referência."
)

tabs = st.tabs([
    "🧾 Amostras",
    "📥 Espectros",
    "🧪 Análises",
    "🔎 Consultar",
    "📊 Visualizar"
])

# ============================================================
# ABA 1 — AMOSTRAS
# ============================================================
with tabs[0]:
    st.subheader("Cadastrar amostra")

    with st.form("form_sample"):
        c1, c2, c3 = st.columns(3)

        with c1:
            sample_id = st.text_input(
                "ID da amostra",
                placeholder="ETOH_0001"
            )
            fuel_type = st.selectbox(
                "Combustível",
                ["Etanol hidratado", "Gasolina"]
            )
            municipality = st.text_input(
                "Município / origem",
                placeholder="São Luís - MA"
            )

        with c2:
            collection_date = st.date_input(
                "Data de coleta",
                value=date.today()
            )
            distributor = st.text_input(
                "Distribuidor / marca",
                placeholder="Opcional"
            )
            lot = st.text_input(
                "Lote",
                placeholder="Opcional"
            )

        with c3:
            source_type = st.selectbox(
                "Tipo de origem",
                [
                    "Posto de combustível",
                    "Distribuidora",
                    "Laboratório",
                    "Amostra preparada",
                    "Outro"
                ]
            )
            collector = st.text_input(
                "Responsável pela coleta",
                placeholder="Opcional"
            )
            notes = st.text_area("Observações")

        save_sample = st.form_submit_button(
            "Registrar amostra",
            type="primary",
            use_container_width=True
        )

    if save_sample:
        sid = sample_id.strip()

        if not sid:
            st.error("Informe o ID da amostra.")
        elif sample_exists(sid):
            st.warning(
                f"A amostra {sid} já está cadastrada. "
                "Use o mesmo ID para adicionar espectros e análises."
            )
        else:
            record = {
                "sample_id": sid,
                "fuel_type": fuel_type,
                "municipality": municipality.strip() or None,
                "collection_date": collection_date.isoformat(),
                "distributor": distributor.strip() or None,
                "lot": lot.strip() or None,
                "source_type": source_type,
                "collector": collector.strip() or None,
                "notes": notes.strip() or None,
            }

            try:
                supabase.table("samples").insert(record).execute()
                st.success(f"Amostra {sid} registrada.")
            except Exception as exc:
                st.error("Não foi possível registrar a amostra.")
                st.exception(exc)

    st.divider()
    st.subheader("Amostras cadastradas")

    try:
        samples_df = get_samples()
        if samples_df.empty:
            st.info("Nenhuma amostra cadastrada.")
        else:
            show_cols = [
                "sample_id", "fuel_type", "municipality",
                "collection_date", "distributor", "lot",
                "source_type", "created_at"
            ]
            show_cols = [c for c in show_cols if c in samples_df.columns]
            st.dataframe(
                samples_df[show_cols],
                use_container_width=True,
                hide_index=True
            )
    except Exception as exc:
        st.error("Erro ao consultar amostras.")
        st.exception(exc)


# ============================================================
# ABA 2 — ESPECTROS
# ============================================================
with tabs[1]:
    st.subheader("Registrar aquisição espectral")

    try:
        samples_df = get_samples()
    except Exception as exc:
        st.error("Erro ao carregar a lista de amostras.")
        st.exception(exc)
        samples_df = pd.DataFrame()

    if samples_df.empty:
        st.info(
            "Cadastre uma amostra na aba 'Amostras' antes de adicionar espectros."
        )
    else:
        sample_options = samples_df["sample_id"].tolist()

        selected_sample = st.selectbox(
            "Amostra",
            sample_options,
            key="spectra_sample"
        )

        uploaded = st.file_uploader(
            "Carregue o espectro",
            type=["csv", "txt"],
            key="spectra_upload"
        )

        spectrum_df = None
        uploaded_bytes = None

        if uploaded is not None:
            uploaded_bytes = uploaded.getvalue()
            try:
                spectrum_df = parse_spectrum_bytes(
                    uploaded_bytes,
                    uploaded.name
                )
                st.success(
                    f"Arquivo lido com sucesso: {len(spectrum_df)} pontos."
                )
                st.plotly_chart(
                    spectrum_plot(spectrum_df),
                    use_container_width=True
                )
            except Exception as exc:
                st.error(str(exc))

        with st.form("form_spectrum"):
            c1, c2, c3 = st.columns(3)

            with c1:
                replicate = st.number_input(
                    "Replicata",
                    min_value=1,
                    max_value=99,
                    value=1,
                    step=1
                )
                acquisition_date = st.date_input(
                    "Data de aquisição",
                    value=date.today(),
                    key="acq_date"
                )

            with c2:
                instrument = st.text_input(
                    "Instrumento",
                    value="Shimadzu IRPrestige-21"
                )
                atr_accessory = st.text_input(
                    "Acessório ATR",
                    value="A confirmar"
                )
                resolution = st.selectbox(
                    "Resolução espectral (cm⁻¹)",
                    [0.5, 1.0, 2.0, 4.0, 8.0, 16.0],
                    index=3
                )

            with c3:
                scans = st.selectbox(
                    "Número de varreduras",
                    [16, 32, 64, 100],
                    index=1
                )
                operator = st.text_input(
                    "Operador",
                    placeholder="Opcional"
                )
                spectral_notes = st.text_area(
                    "Observações da aquisição"
                )

            acquisition_id = (
                f"{safe_component(selected_sample)}_R{int(replicate):02d}"
            )
            st.caption(
                f"ID de aquisição previsto: **{acquisition_id}**"
            )

            save_spectrum = st.form_submit_button(
                "Registrar aquisição espectral",
                type="primary",
                use_container_width=True
            )

        if save_spectrum:
            if uploaded is None or uploaded_bytes is None or spectrum_df is None:
                st.error("Carregue um espectro válido.")
            elif acquisition_exists(acquisition_id):
                st.error(
                    f"A aquisição {acquisition_id} já existe. "
                    "Altere a replicata."
                )
            else:
                sample_row = samples_df.loc[
                    samples_df["sample_id"] == selected_sample
                ].iloc[0]

                fuel_folder = (
                    "etanol"
                    if sample_row["fuel_type"] == "Etanol hidratado"
                    else "gasolina"
                )

                original_name = safe_component(Path(uploaded.name).name)

                storage_path = (
                    f"{fuel_folder}/"
                    f"{safe_component(selected_sample)}/"
                    f"{acquisition_id}_{original_name}"
                )

                record = {
                    "sample_id": selected_sample,
                    "acquisition_id": acquisition_id,
                    "acquisition_date": acquisition_date.isoformat(),
                    "instrument": instrument.strip() or None,
                    "atr_accessory": atr_accessory.strip() or None,
                    "resolution_cm1": float(resolution),
                    "scans": int(scans),
                    "replicate": int(replicate),
                    "operator": operator.strip() or None,
                    "original_filename": uploaded.name,
                    "storage_path": storage_path,
                    "spectral_points": int(len(spectrum_df)),
                    "wavenumber_max": float(
                        spectrum_df["wavenumber"].max()
                    ),
                    "wavenumber_min": float(
                        spectrum_df["wavenumber"].min()
                    ),
                    "notes": spectral_notes.strip() or None,
                }

                try:
                    upload_spectrum(
                        storage_path,
                        uploaded_bytes,
                        uploaded.name
                    )
                    try:
                        supabase.table(
                            "spectral_acquisitions"
                        ).insert(record).execute()
                    except Exception:
                        remove_spectrum_if_needed(storage_path)
                        raise

                    st.success(
                        f"{acquisition_id} registrado permanentemente."
                    )
                    st.info(
                        f"Arquivo: {BUCKET}/{storage_path}"
                    )

                except Exception as exc:
                    st.error(
                        "Não foi possível registrar a aquisição."
                    )
                    st.exception(exc)


# ============================================================
# ABA 3 — ANÁLISES DE REFERÊNCIA
# ============================================================
with tabs[2]:
    st.subheader("Registrar resultado analítico")

    try:
        samples_df = get_samples()
    except Exception as exc:
        st.error("Erro ao carregar amostras.")
        st.exception(exc)
        samples_df = pd.DataFrame()

    if samples_df.empty:
        st.info(
            "Cadastre uma amostra antes de adicionar resultados analíticos."
        )
    else:
        with st.form("form_analysis"):
            c1, c2, c3 = st.columns(3)

            with c1:
                analysis_sample = st.selectbox(
                    "Amostra",
                    samples_df["sample_id"].tolist(),
                    key="analysis_sample"
                )
                analyte = st.text_input(
                    "Parâmetro / analito",
                    placeholder="Ex.: Metanol"
                )
                result = st.text_input(
                    "Resultado",
                    placeholder="Ex.: 0.12"
                )

            with c2:
                unit = st.text_input(
                    "Unidade",
                    placeholder="Ex.: % v/v"
                )
                method = st.text_input(
                    "Método",
                    placeholder="Ex.: CG-FID"
                )
                analysis_date = st.date_input(
                    "Data da análise",
                    value=date.today(),
                    key="analysis_date"
                )

            with c3:
                conformity = st.selectbox(
                    "Conformidade",
                    ["Conforme", "Não conforme", "Não avaliada"],
                    index=2
                )
                laboratory = st.text_input(
                    "Laboratório",
                    placeholder="Opcional"
                )
                uncertainty = st.text_input(
                    "Incerteza",
                    placeholder="Opcional"
                )

            analysis_notes = st.text_area(
                "Observações da análise"
            )

            save_analysis = st.form_submit_button(
                "Registrar análise",
                type="primary",
                use_container_width=True
            )

        if save_analysis:
            if not analyte.strip():
                st.error("Informe o parâmetro/analito.")
            elif not result.strip():
                st.error("Informe o resultado.")
            else:
                value = nullable_float(
                    result.replace(",", ".")
                )

                if value is None:
                    st.error(
                        "O resultado deve ser numérico. "
                        "Use ponto ou vírgula como separador decimal."
                    )
                else:
                    record = {
                        "sample_id": analysis_sample,
                        "analyte": analyte.strip(),
                        "result": value,
                        "unit": unit.strip() or None,
                        "method": method.strip() or None,
                        "analysis_date": analysis_date.isoformat(),
                        "conformity": conformity,
                        "laboratory": laboratory.strip() or None,
                        "uncertainty": uncertainty.strip() or None,
                        "notes": analysis_notes.strip() or None,
                    }

                    try:
                        supabase.table(
                            "reference_analyses"
                        ).insert(record).execute()
                        st.success(
                            f"Resultado de {analyte.strip()} registrado "
                            f"para {analysis_sample}."
                        )
                    except Exception as exc:
                        st.error(
                            "Não foi possível registrar a análise."
                        )
                        st.exception(exc)


# ============================================================
# ABA 4 — CONSULTA
# ============================================================
with tabs[3]:
    st.subheader("Consulta integrada")

    try:
        samples_df = get_samples()
        spectra_df = query_table(
            "spectral_acquisitions",
            "created_at"
        )
        analyses_df = query_table(
            "reference_analyses",
            "created_at"
        )
    except Exception as exc:
        st.error("Erro ao consultar o banco.")
        st.exception(exc)
        samples_df = pd.DataFrame()
        spectra_df = pd.DataFrame()
        analyses_df = pd.DataFrame()

    if samples_df.empty:
        st.info("Nenhuma amostra cadastrada.")
    else:
        selected = st.selectbox(
            "Selecione a amostra",
            samples_df["sample_id"].tolist(),
            key="query_sample"
        )

        sample_row = samples_df.loc[
            samples_df["sample_id"] == selected
        ]

        st.markdown("#### Amostra")
        st.dataframe(
            sample_row,
            use_container_width=True,
            hide_index=True
        )

        st.markdown("#### Aquisições espectrais")
        if spectra_df.empty:
            st.info("Nenhuma aquisição registrada.")
        else:
            sub = spectra_df[
                spectra_df["sample_id"] == selected
            ]
            if sub.empty:
                st.info(
                    "Nenhuma aquisição espectral para esta amostra."
                )
            else:
                st.dataframe(
                    sub,
                    use_container_width=True,
                    hide_index=True
                )

        st.markdown("#### Análises de referência")
        if analyses_df.empty:
            st.info("Nenhuma análise registrada.")
        else:
            sub = analyses_df[
                analyses_df["sample_id"] == selected
            ]
            if sub.empty:
                st.info(
                    "Nenhum resultado analítico para esta amostra."
                )
            else:
                st.dataframe(
                    sub,
                    use_container_width=True,
                    hide_index=True
                )

        # Exportação integrada simples
        package_rows = []

        for _, row in sample_row.iterrows():
            package_rows.append({
                "record_type": "sample",
                **row.to_dict()
            })

        if not spectra_df.empty:
            for _, row in spectra_df[
                spectra_df["sample_id"] == selected
            ].iterrows():
                package_rows.append({
                    "record_type": "spectral_acquisition",
                    **row.to_dict()
                })

        if not analyses_df.empty:
            for _, row in analyses_df[
                analyses_df["sample_id"] == selected
            ].iterrows():
                package_rows.append({
                    "record_type": "reference_analysis",
                    **row.to_dict()
                })

        export_df = pd.DataFrame(package_rows)

        st.download_button(
            "Baixar metadados desta amostra (.csv)",
            data=export_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{selected}_metadata.csv",
            mime="text/csv"
        )


# ============================================================
# ABA 5 — VISUALIZAÇÃO
# ============================================================
with tabs[4]:
    st.subheader("Visualizar espectro")

    try:
        spectra_df = (
            supabase.table("spectral_acquisitions")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        spectra_df = pd.DataFrame(spectra_df.data or [])
    except Exception as exc:
        st.error("Erro ao consultar aquisições.")
        st.exception(exc)
        spectra_df = pd.DataFrame()

    if spectra_df.empty:
        st.info("Nenhuma aquisição espectral registrada.")
    else:
        chosen = st.selectbox(
            "Aquisição",
            spectra_df["acquisition_id"].tolist(),
            key="view_acq"
        )

        row = spectra_df.loc[
            spectra_df["acquisition_id"] == chosen
        ].iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Amostra", str(row["sample_id"]))
        c2.metric("Replicata", str(row["replicate"]))
        c3.metric(
            "Resolução",
            f"{row['resolution_cm1']} cm⁻¹"
        )
        c4.metric("Varreduras", str(row["scans"]))

        try:
            file_bytes = download_spectrum(
                row["storage_path"]
            )
            df_plot = parse_spectrum_bytes(
                file_bytes,
                row.get("original_filename", "spectrum.csv")
            )

            st.plotly_chart(
                spectrum_plot(df_plot, chosen),
                use_container_width=True
            )

            st.download_button(
                "Baixar espectro original",
                data=file_bytes,
                file_name=row.get(
                    "original_filename",
                    f"{chosen}.csv"
                ),
                mime="application/octet-stream"
            )

        except Exception as exc:
            st.error(
                "O registro existe, mas o arquivo não pôde ser "
                "recuperado do Storage."
            )
            st.exception(exc)

st.divider()
st.caption(
    "Banco Espectral ATR-FTIR | "
    "Streamlit + Supabase PostgreSQL + Supabase Storage"
)

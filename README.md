
# Protótipo — Banco Espectral ATR-FTIR

MVP em Streamlit para:

- carregar espectros ATR-FTIR em CSV/TXT;
- visualizar o espectro;
- cadastrar metadados da amostra e da aquisição;
- registrar os dados em SQLite;
- preservar o arquivo espectral original;
- consultar e filtrar os registros;
- exportar metadados;
- reabrir e visualizar espectros já cadastrados.

## Estrutura

```text
ftir_streamlit_prototipo/
├── app.py
├── requirements.txt
├── exemplo_etanol_ftir.csv
├── README.md
├── spectra/              # criada/usar durante execução
└── ftir_database.db      # criado automaticamente
```

## Como executar

No terminal:

```bash
cd ftir_streamlit_prototipo
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Formato do espectro

O protótipo espera duas colunas:

```text
wavenumber,intensity
4000,0.102
3996,0.103
...
```

A primeira representa o número de onda em cm⁻¹ e a segunda a
intensidade ou absorbância.

O arquivo `exemplo_etanol_ftir.csv` é sintético e serve apenas para
demonstração da interface.

## Observação

Nesta primeira versão, o banco possui uma tabela única para tornar o
protótipo fácil de apresentar. Na versão de pesquisa, a estrutura pode
ser normalizada em tabelas separadas, por exemplo:

- samples
- spectral_acquisitions
- reference_analyses
- instruments
- models

Isso permite uma arquitetura mais robusta sem complicar o MVP.

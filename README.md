# Banco Espectral ATR-FTIR — Streamlit + Supabase

## O que muda
- Streamlit: interface
- Supabase PostgreSQL: metadados
- Supabase Storage: arquivos espectrais originais

## Passos
1. Crie um projeto no Supabase.
2. No SQL Editor, execute `supabase_schema.sql`.
3. Em Storage, crie um bucket PRIVADO chamado `ftir-spectra`.
4. No Supabase, copie a Project URL e a service_role key.
5. No Streamlit Community Cloud, abra App settings > Secrets.
6. Cole:
   SUPABASE_URL = "..."
   SUPABASE_SERVICE_ROLE_KEY = "..."
   APP_PASSWORD = "..."
7. Substitua `app.py` e `requirements.txt` no GitHub pelo conteúdo deste pacote.
8. Aguarde o redeploy.

## Onde o espectro fica
Exemplo:
ftir-spectra/etanol/ETOH_0001/ETOH_0001_R01_espectro.csv

Os metadados ficam na tabela:
public.spectra

## Segurança
Nunca publique a service_role key no GitHub.
Use apenas o gerenciador de Secrets do Streamlit.
O APP_PASSWORD é opcional, mas recomendado para este protótipo.

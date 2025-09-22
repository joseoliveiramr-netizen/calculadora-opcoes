# app.py
import streamlit as st
import pandas as pd
import io
import re
import csv
from datetime import datetime

st.set_page_config(page_title="Calculadora de Gama e Delta de Opções", layout="wide")


# -------------------------
# Helpers
# -------------------------
def parse_pt_br_date(s):
    """Tenta converter strings com abreviações PT-BR para um formato que pd.to_datetime entenda."""
    if pd.isna(s):
        return s
    s = str(s)
    # meses e dias PT-BR -> EN
    month_map = {
        r'\bJan\b': 'Jan', r'\bFev\b': 'Feb', r'\bMar\b': 'Mar', r'\bAbr\b': 'Apr',
        r'\bMai\b': 'May', r'\bJun\b': 'Jun', r'\bJul\b': 'Jul', r'\bAgo\b': 'Aug',
        r'\bSet\b': 'Sep', r'\bOut\b': 'Oct', r'\bNov\b': 'Nov', r'\bDez\b': 'Dec'
    }
    day_map = {
        r'\bSeg\b': 'Mon', r'\bTer\b': 'Tue', r'\bQua\b': 'Wed', r'\bQui\b': 'Thu',
        r'\bSex\b': 'Fri', r'\bSáb\b': 'Sat', r'\bSab\b': 'Sat', r'\bDom\b': 'Sun'
    }
    for k, v in month_map.items():
        s = re.sub(k, v, s, flags=re.IGNORECASE)
    for k, v in day_map.items():
        s = re.sub(k, v, s, flags=re.IGNORECASE)
    return s


def detect_table_start(lines):
    """Detecta a linha onde começa a tabela de opções (procura por cabeçalho típico)."""
    header_keywords = ['expiration', 'expiration_date', 'calls_ticker', 'calls_gamma', 'strike', 'greve', 'venc', 'vencimento']
    for i, line in enumerate(lines):
        low = line.lower()
        if any(k in low for k in header_keywords) and (low.count(',') >= 3 or low.count(';') >= 3):
            return i
    # fallback: linha 3 (índice 3) como você usava antes, senão 0
    return 3 if len(lines) > 3 else 0


def detect_delimiter(sample):
    """Tenta detectar delimitador com csv.Sniffer; se falhar, retorna ','."""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[',', ';', '\t', '|'])
        return dialect.delimiter, dialect.quotechar
    except Exception:
        # fallback simples: se houver mais ';' do que ',' use ';', se não use ','
        if sample.count(';') > sample.count(','):
            return ';', '"'
        elif sample.count('\t') > 0:
            return '\t', '"'
        else:
            return ',', '"'


def normalize_number_series(s):
    """Converte colunas numéricas que usam '.' como milhar e ',' como decimal para float."""
    if s.dtype == object:
        s = s.astype(str).str.replace(r'\s+', '', regex=True)
        # se tiver ponto e vírgula no mesmo valor, assume '.' é milhar e ',' decimal
        s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)


def map_columns_heuristic(cols):
    """
    Retorna um dicionário que mapeia nomes esperados para substrings a procurar.
    Se um nome for encontrado, será usado.
    """
    mapping_keywords = {
        'Expiration_Date': ['expiration', 'expiration_date', 'venc', 'vencimento', 'data'],
        'Calls_Ticker': ['calls_ticker', 'call_ticker', 'calls ticker', 'call'],
        'Calls_Last_Sale': ['last_sale', 'last sale', 'ultimo', 'último', 'lastsale'],
        'Calls_Net': ['calls_net', 'net'],
        'Calls_Bid': ['calls_bid', 'bid'],
        'Calls_Ask': ['calls_ask', 'ask'],
        'Calls_Volume': ['calls_volume', 'volume', 'vol'],
        'Calls_IV': ['calls_iv', 'iv', 'impl_vol', 'implied'],
        'Calls_Delta': ['calls_delta', 'delta', 'call_delta'],
        'Calls_Gamma': ['calls_gamma', 'gamma', 'call_gamma'],
        'Calls_Open_Interest': ['calls_open_interest', 'open_interest', 'open interest', 'oi'],
        'Strike': ['strike', 'greve', 'preco', 'preço', 'exercise'],
        'Puts_Ticker': ['puts_ticker', 'put_ticker', 'puts ticker', 'put'],
        'Puts_Last_Sale': ['puts_last_sale', 'puts last', 'put_last'],
        'Puts_Net': ['puts_net', 'net'],
        'Puts_Bid': ['puts_bid', 'bid'],
        'Puts_Ask': ['puts_ask', 'ask'],
        'Puts_Volume': ['puts_volume', 'volume', 'vol'],
        'Puts_IV': ['puts_iv', 'iv'],
        'Puts_Delta': ['puts_delta', 'delta', 'put_delta'],
        'Puts_Gamma': ['puts_gamma', 'gamma', 'put_gamma'],
        'Puts_Open_Interest': ['puts_open_interest', 'open_interest', 'open interest', 'oi']
    }
    found = {}
    cols_low = [c.lower() for c in cols]
    for target, keys in mapping_keywords.items():
        for i, c in enumerate(cols_low):
            for key in keys:
                if key.replace(' ', '') in re.sub(r'[^a-z0-9]', '', c):
                    found[target] = cols[i]
                    break
            if target in found:
                break
    return found, list(mapping_keywords.keys())


# -------------------------
# App UI
# -------------------------
st.title("📊 Calculadora de Gama e Delta de Opções (robusta)")

uploaded_file = st.file_uploader("Faça o upload de um arquivo CSV de opções", type=["csv"])

if uploaded_file is None:
    st.info("Faça upload de um arquivo CSV para iniciar os cálculos.")
else:
    raw = uploaded_file.read()
    try:
        text = raw.decode('utf-8-sig')
    except Exception:
        text = raw.decode('latin1', errors='replace')

    lines = text.splitlines()

    # Tenta extrair Bid/Ask/Spot do cabeçalho (primeiras 6 linhas)
    header_text = "\n".join(lines[:6])
    bid_value = None
    ask_value = None
    data_arquivo_str = None
    m = re.search(r'Bid[:\s]*([0-9\.\,]+)', header_text, flags=re.IGNORECASE)
    if m:
        bid_value = float(m.group(1).replace('.', '').replace(',', '.'))
    m2 = re.search(r'Ask[:\s]*([0-9\.\,]+)', header_text, flags=re.IGNORECASE)
    if m2:
        ask_value = float(m2.group(1).replace('.', '').replace(',', '.'))
    # fallback: procura "Localização:" ou "Spot:" ou "Preço:"
    if bid_value is None:
        m3 = re.search(r'Localiza[oõ]?[c]?a[:\s]*([0-9\.\,]+)', header_text, flags=re.IGNORECASE)
        if m3:
            bid_value = float(m3.group(1).replace('.', '').replace(',', '.'))

    spot_value = bid_value if bid_value is not None else (ask_value if ask_value is not None else 0.0)

    st.subheader("Informações extraídas do cabeçalho")
    st.write(f"Spot (estimado): {spot_value:,.2f}" if spot_value else "Spot não encontrado")
    st.write(f"Bid: {bid_value:,.2f}" if bid_value else "Bid: N/A")
    st.write(f"Ask: {ask_value:,.2f}" if ask_value else "Ask: N/A")

    # Detecta onde começa a tabela
    start_idx = detect_table_start(lines)
    sample = "\n".join(lines[start_idx:start_idx + 6]) if start_idx < len(lines) else "\n".join(lines)
    delimiter, quotechar = detect_delimiter(sample)

    st.write(f"Detectado início da tabela na linha: {start_idx} (0-indexed). Delimitador estimado: '{delimiter}'")

    data_io = io.StringIO("\n".join(lines[start_idx:]))

    # Lê com pandas (engine python tende a ser mais tolerante)
    try:
        df = pd.read_csv(data_io, sep=delimiter, engine='python', quotechar=quotechar)
    except Exception as e:
        st.warning(f"Leitura com sep='{delimiter}' falhou: {e}. Tentando leitura com engine='python' e sep=','...")
        data_io.seek(0)
        try:
            df = pd.read_csv(data_io, sep=',', engine='python', quotechar=quotechar)
        except Exception as e2:
            st.error(f"Não foi possível ler a tabela automaticamente: {e2}")
            st.text("Exiba as primeiras 30 linhas do CSV para debug:")
            st.text("\n".join(lines[:30]))
            raise

    st.subheader("Colunas detectadas na tabela")
    st.write(df.columns.tolist())

    # Tenta mapear colunas heurísticamente
    found_map, expected_order = map_columns_heuristic(df.columns.tolist())
    st.write("Mapeamento heurístico encontrado (parcial):")
    st.write(found_map)

    # Se não encontrou mapeamento consistente, mas número de colunas bate com o esperado, força renomear pela ordem
    if len(found_map) < 10 and len(df.columns) == len(expected_order):
        st.info("Poucos nomes detectados automaticamente, mas quantidade de colunas bate com o esperado -> assumindo ordem padrão.")
        df.columns = expected_order
        # rebuild mapping as identity
        found_map = {k: k for k in expected_order}

    # Constrói um DataFrame 'padronizado' com as colunas desejadas (preenchendo zeros se faltarem)
    std_cols = expected_order
    df_std = pd.DataFrame()
    for col in std_cols:
        if col in found_map:
            df_std[col] = df[found_map[col]]
        elif col in df.columns:
            df_std[col] = df[col]
        else:
            # coluna ausente: cria zero/empty
            df_std[col] = 0

    # Converte colunas numéricas
    numeric_cols = [
        'Calls_Last_Sale', 'Puts_Last_Sale', 'Calls_Volume', 'Puts_Volume',
        'Calls_IV', 'Puts_IV', 'Calls_Delta', 'Puts_Delta',
        'Calls_Gamma', 'Puts_Gamma', 'Calls_Open_Interest', 'Puts_Open_Interest', 'Strike'
    ]
    for col in numeric_cols:
        if col in df_std.columns:
            try:
                df_std[col] = normalize_number_series(df_std[col])
            except Exception:
                df_std[col] = pd.to_numeric(df_std[col], errors='coerce').fillna(0)

    # Inicializa colunas de exposição
    df_std['Calls_Gamma_Exposure'] = 0.0
    df_std['Puts_Gamma_Exposure'] = 0.0
    df_std['Calls_Delta_Exposure'] = 0.0
    df_std['Puts_Delta_Exposure'] = 0.0

    # Calcula exposições (usa multiplier 100 e spot se disponível)
    try:
        multiplier = 100
        if spot_value and spot_value != 0:
            df_std['Calls_Gamma_Exposure'] = df_std['Calls_Gamma'] * df_std['Calls_Open_Interest'] * multiplier * spot_value
            df_std['Puts_Gamma_Exposure'] = df_std['Puts_Gamma'] * df_std['Puts_Open_Interest'] * multiplier * spot_value * -1

            df_std['Calls_Delta_Exposure'] = df_std['Calls_Delta'] * df_std['Calls_Open_Interest'] * multiplier * spot_value
            df_std['Puts_Delta_Exposure'] = df_std['Puts_Delta'] * df_std['Puts_Open_Interest'] * multiplier * spot_value
        else:
            st.warning("Spot não encontrado. As exposições serão calculadas com Spot = 0 (resultado zero).")
    except Exception as e:
        st.error(f"Erro ao calcular exposições: {e}")

    st.subheader("Pré-visualização (pré-processado)")
    st.dataframe(df_std.head())

    # --- Datas / DTE ---
    try:
        # aplica tradução PT-BR e parse
        df_std['Expiration_Date_Parsed'] = pd.to_datetime(
            df_std['Expiration_Date'].apply(parse_pt_br_date),
            errors='coerce'
        )
        df_std['Expiration_Date_Parsed'] = df_std['Expiration_Date_Parsed'].fillna(
            pd.to_datetime(df_std['Expiration_Date'], dayfirst=True, errors='coerce')
        )
        df_std['Expiration_Date_Parsed'] = pd.to_datetime(df_std['Expiration_Date_Parsed'], errors='coerce')

        today_dt = pd.to_datetime(datetime.now().date())
        df_std['Days_To_Expiration'] = (df_std['Expiration_Date_Parsed'] - today_dt).dt.days

        st.subheader(f"Zero DTE (data atual: {datetime.now().date().strftime('%Y-%m-%d')})")
        zero_dte_options = df_std[df_std['Days_To_Expiration'] == 0]
        if not zero_dte_options.empty:
            st.dataframe(zero_dte_options[[
                'Expiration_Date', 'Strike', 'Calls_Open_Interest', 'Puts_Open_Interest',
                'Calls_Gamma_Exposure', 'Puts_Gamma_Exposure', 'Calls_Delta_Exposure', 'Puts_Delta_Exposure'
            ]].head())
        else:
            st.info("Nenhuma opção com Zero DTE encontrada para a data atual.")
    except Exception as e:
        st.error(f"Erro ao calcular DTE: {e}")

    # --- Sumarizado ---
    total_calls_gamma_exposure = df_std['Calls_Gamma_Exposure'].sum()
    total_puts_gamma_exposure = df_std['Puts_Gamma_Exposure'].sum()
    total_net_gamma_exposure = total_calls_gamma_exposure + total_puts_gamma_exposure

    total_calls_delta_exposure = df_std['Calls_Delta_Exposure'].sum()
    total_puts_delta_exposure = df_std['Puts_Delta_Exposure'].sum()
    total_net_delta_exposure = total_calls_delta_exposure + total_puts_delta_exposure

    st.subheader("Resultados Sumarizados")
    st.write(f"**Exposição Total Gama (Calls):** {total_calls_gamma_exposure:,.2f}")
    st.write(f"**Exposição Total Gama (Puts):** {total_puts_gamma_exposure:,.2f}")
    st.write(f"**Exposição Gama Líquida (Net):** {total_net_gamma_exposure:,.2f}")
    st.write("---")
    st.write(f"**Exposição Total Delta (Calls):** {total_calls_delta_exposure:,.2f}")
    st.write(f"**Exposição Total Delta (Puts):** {total_puts_delta_exposure:,.2f}")
    st.write(f"**Exposição Delta Líquida (Net):** {total_net_delta_exposure:,.2f}")

    st.success("Processamento concluído.")

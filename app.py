import streamlit as st
import pandas as pd
import io
from datetime import datetime

def main():
    st.title("Calculadora de Gama e Delta de Opções")

    st.write("Faça o upload de um arquivo CSV de dados de opções para realizar os cálculos.")

    uploaded_file = st.file_uploader("Escolha um arquivo CSV", type="csv")

    if uploaded_file is not None:
        string_data = uploaded_file.read().decode('utf-8')
        lines = string_data.splitlines()

        # --- 1. Extrair informações do cabeçalho / resumo ---
        spot_value = None
        bid_value = None
        ask_value = None
        data_arquivo_str = None 

        if len(lines) > 2: # Garante que a linha 3 (índice 2) existe
            line2_content = lines[2] # Esta é a linha que contém Bid/Ask
            line2_parts = [p.strip() for p in line2_content.split(',')]
            
            for part in line2_parts:
                if part.startswith("Data:"):
                    try:
                        data_part = part.split('às')[0].replace('Data:', '').strip()
                        data_arquivo_str = data_part
                    except:
                        pass
                
                if part.startswith("Bid:"):
                    # Remover ponto de milhar e trocar vírgula por ponto para float
                    bid_value = float(part.split(':')[1].strip().replace('.', '').replace(',', '.'))
                elif part.startswith("Ask:"):
                    ask_value = float(part.split(':')[1].strip().replace('.', '').replace(',', '.'))
            
            spot_value = bid_value if bid_value is not None else 0.0

        st.subheader(f"Informações Gerais (Extraídas do CSV)")
        # Corrigindo o Spot/Bid/Ask para mostrar o valor correto, não deslocado
        st.write(f"**Spot:** {spot_value / 100:,.2f}" if spot_value is not None else "**Spot:** N/A") # Dividir por 100 se o valor estiver 100x maior
        st.write(f"**Bid:** {bid_value / 100:,.2f}" if bid_value is not None else "**Bid:** N/A") # Dividir por 100 se o valor estiver 100x maior
        st.write(f"**Ask:** {ask_value / 100:,.2f}" if ask_value is not None else "**Ask:** N/A") # Dividir por 100 se o valor estiver 100x maior
        st.write(f"**Data do arquivo:** {data_arquivo_str if data_arquivo_str else 'N/A'}")


        # --- 2. Ler a Tabela de Opções ---
        options_data_io = io.StringIO("\n".join(lines[3:])) 

        try:
            df_options = pd.read_csv(options_data_io)
            
            # --- Limpeza e Renomeação de Colunas (AGORA COM NOMES EM PORTUGUÊS EXATOS) ---
            df_options.columns = df_options.columns.str.strip()

            # Mapeamento de nomes de colunas do CSV (EXATAMENTE como o Pandas as leu) para nomes padronizados no código
            column_mapping = {
                'Data de validade': 'Expiration_Date', 
                'Calls': 'Calls_Ticker', # EXATO: 'Calls'
                'Última venda': 'Calls_Last_Sale',
                'Rede': 'Calls_Net', 
                'Bid': 'Calls_Bid', # EXATO: 'Bid'
                'Ask': 'Calls_Ask', # EXATO: 'Ask'
                'Volume': 'Calls_Volume', # EXATO: 'Volume'
                'IV': 'Calls_IV', # EXATO: 'IV'
                'Delta': 'Calls_Delta', # EXATO: 'Delta'
                'Gama': 'Calls_Gamma', # EXATO: 'Gama'
                'Contratos em aberto': 'Calls_Open_Interest', # EXATO: 'Contratos em aberto'
                'Strike': 'Strike', # EXATO: 'Strike'
                'Puts': 'Puts_Ticker', # EXATO: 'Puts'
                'Última venda.1': 'Puts_Last_Sale',
                'Net.1': 'Puts_Net', # EXATO: 'Net.1'
                'Bid.1': 'Puts_Bid', # EXATO: 'Bid.1'
                'Ask.1': 'Puts_Ask', # EXATO: 'Ask.1'
                'Volume.1': 'Puts_Volume', # EXATO: 'Volume.1'
                'IV.1': 'Puts_IV', # EXATO: 'IV.1'
                'Delta.1': 'Puts_Delta', # EXATO: 'Delta.1'
                'Gama.1': 'Puts_Gamma', # EXATO: 'Gama.1'
                'Contratos em aberto.1': 'Puts_Open_Interest' # EXATO: 'Contratos em aberto.1'
            }
            
            df_options.rename(columns=column_mapping, inplace=True)

            # --- AQUI: Imprimindo os nomes finais das colunas APÓS o renomeio para depuração ---
            # st.write("Nomes das colunas após renomeio:", df_options.columns.tolist()) 

            # Verificar se as colunas essenciais existem após o renomeio
            required_cols = ['Expiration_Date', 'Strike', 'Calls_Open_Interest', 'Calls_Gamma',
                             'Puts_Open_Interest', 'Puts_Gamma', 'Calls_Delta', 'Puts_Delta']
            
            missing_cols = [col for col in required_cols if col not in df_options.columns]
            if missing_cols:
                st.error(f"Colunas essenciais ausentes após renomeio: {missing_cols}. Verifique o cabeçalho do seu CSV.")
                st.write("Colunas disponíveis no DataFrame (após tentar renomear):", df_options.columns.tolist())
                return 
            
            st.subheader("Dados da Tabela de Opções (pré-processados)")
            st.dataframe(df_options)


            # --- Converter colunas numéricas ---
            cols_to_convert = [
                'Calls_Last_Sale', 'Puts_Last_Sale', 'Calls_Volume', 'Puts_Volume',
                'Calls_IV', 'Puts_IV', 'Calls_Delta', 'Puts_Delta',
                'Calls_Gamma', 'Puts_Gamma', 'Calls_Open_Interest', 'Puts_Open_Interest', 'Strike'
            ]

            for col in cols_to_convert:
                if col in df_options.columns:
                    df_options[col] = df_options[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                    df_options[col] = pd.to_numeric(df_options[col], errors='coerce')
            
            df_options.fillna(0, inplace=True)

            # --- Cálculos de Exposição Gama e Delta ---

            if spot_value is not None and spot_value != 0:
                multiplier = 100 
                # Se o spot_value for 100x maior, divida por 100 para o cálculo
                calculated_spot = spot_value / 100 
                
                df_options['Call_Gamma_Exposure'] = df_options['Calls_Gamma'] * df_options['Calls_Open_Interest'] * multiplier * calculated_spot
                df_options['Put_Gamma_Exposure'] = df_options['Puts_Gamma'] * df_options['Puts_Open_Interest'] * multiplier * calculated_spot * -1 

                df_options['Call_Delta_Exposure'] = df_options['Calls_Delta'] * df_options['Calls_Open_Interest'] * multiplier * calculated_spot
                df_options['Put_Delta_Exposure'] = df_options['Puts_Delta'] * df_options['Puts_Open_Interest'] * multiplier * calculated_spot
            else:
                st.warning("Não foi possível determinar o valor do Spot para calcular a Exposição Gama e Delta. Certifique-se de que a linha 3 do CSV contém 'Bid:'.")
                df_options['Call_Gamma_Exposure'] = 0
                df_options['Put_Gamma_Exposure'] = 0
                df_options['Call_Delta_Exposure'] = 0
                df_options['Put_Delta_Exposure'] = 0


            st.subheader("Cálculos por Opção (Exposição Gama e Delta)")
            st.dataframe(df_options[['Expiration_Date', 'Strike', 
                                     'Calls_Open_Interest', 'Calls_Gamma', 'Call_Gamma_Exposure', 'Calls_Delta', 'Call_Delta_Exposure',
                                     'Puts_Open_Interest', 'Puts_Gamma', 'Put_Gamma_Exposure', 'Puts_Delta', 'Put_Delta_Exposure']]) 


            # --- Somar a exposição em gama e delta (Calls, Puts, Net) ---
            total_call_gamma_exposure = df_options['Call_Gamma_Exposure'].sum()
            total_put_gamma_exposure = df_options['Put_Gamma_Exposure'].sum()
            total_net_gamma_exposure = total_call_gamma_exposure + total_put_gamma_exposure

            total_call_delta_exposure = df_options['Call_Delta_Exposure'].sum()
            total_put_delta_exposure = df_options['Put_Delta_Exposure'].sum()
            total_net_delta_exposure = total_call_delta_exposure + total_put_delta_exposure

            st.subheader("Resultados Sumarizados")
            st.write(f"**Exposição Total Gama (Calls):** {total_call_gamma_exposure:,.2f}")
            st.write(f"**Exposição Total Gama (Puts):** {total_put_gamma_exposure:,.2f}")
            st.write(f"**Exposição Gama Líquida (Net):** {total_net_gamma_exposure:,.2f}")
            st.write("---")
            st.write(f"**Exposição Total Delta (Calls):** {total_call_delta_exposure:,.2f}")
            st.write(f"**Exposição Total Delta (Puts):** {total_put_delta_exposure:,.2f}")
            st.write(f"**Exposição Delta Líquida (Net):** {total_net_delta_exposure:,.2f}")


            # --- Separar Zero DTE (Days to Expiration) e outras datas ---
            try:
                df_options['Expiration_Date_Parsed'] = pd.to_datetime(df_options['Expiration_Date'], format='%a %b %d %Y', errors='coerce')
                
                today_date = datetime.now().date()
                
                df_options['Days_To_Expiration'] = (df_options['Expiration_Date_Parsed'].dt.date - today_date).dt.days
                
                st.subheader(f"Zero DTE (Opções com 0 Dias para o Vencimento - data atual: {today_date.strftime('%Y-%m-%d')})")
                zero_dte_options = df_options[df_options['Days_To_Expiration'] == 0]
                if not zero_dte_options.empty:
                    st.dataframe(zero_dte_options[['Expiration_Date', 'Strike', 'Calls_Open_Interest', 'Puts_Open_Interest', 'Call_Gamma_Exposure', 'Put_Gamma_Exposure', 'Calls_Delta_Exposure', 'Puts_Delta_Exposure']])
                else:
                    st.write("Nenhuma opção com Zero DTE encontrada para a data atual.")
                
                st.subheader(f"Opções com 1 DTE (Dias para o Vencimento)")
                one_dte_options = df_options[df_options['Days_To_Expiration'] == 1]
                if not one_dte_options.empty:
                    st.dataframe(one_dte_options[['Expiration_Date', 'Strike', 'Calls_Open_Interest', 'Puts_Open_Interest', 'Call_Gamma_Exposure', 'Put_Gamma_Exposure', 'Calls_Delta_Exposure', 'Puts_Delta_Exposure']])
                else:
                    st.write("Nenhuma opção com 1 DTE encontrada.")

            except Exception as e:
                st.warning(f"Não foi possível calcular Dias para o Vencimento (DTE): {e}. Verifique o formato da data de vencimento 'Qua Set 03 2025' no CSV.")


        except Exception as e:
            st.error(f"Erro inesperado ao processar o CSV: {e}")
            st.text("Conteúdo do CSV (primeiras 10 linhas):")
            st.text("\n".join(lines[:10]))
            st.text("Verifique se o cabeçalho das colunas em português foi renomeado corretamente.")


if __name__ == "__main__":
    main()

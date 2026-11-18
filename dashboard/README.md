# Dashboard GeoGoiás

Painel Streamlit que lê diretamente a árvore pública do repositório `LeandraCordeiro/Base-GeoGoi-s`.

## Publicar no Streamlit Community Cloud
1. Envie a pasta `dashboard/` para a raiz do repositório GitHub.
2. Acesse https://share.streamlit.io e conecte o GitHub.
3. Selecione `LeandraCordeiro/Base-GeoGoi-s`, branch `main`.
4. No campo de arquivo principal informe `dashboard/app.py`.
5. Clique em **Deploy**. O arquivo `dashboard/requirements.txt` é identificado automaticamente.

## Catálogo opcional

Pode-se acrescentar `07_metadados/catalogo_mestre.csv` (UTF-8), com colunas como:

`caminho,titulo,instituicao,municipio,substancia,latitude,longitude,fonte,ano,tipo,tema`

Os dados geográficos só são exibidos quando coordenadas são fornecidas explicitamente. O inventário usa a API pública do GitHub e cache de 15 minutos.

**Atenção**: contagens de arquivos não indicam cobertura geológica nem estimativas de reservas, oferta ou demanda.

# SmartPark Sim

Sistema IoT de monitoramento de vagas de estacionamento, simulado no Wokwi, com API REST e painel web.
Projeto da disciplina de Arquitetura de Computadores.

## Links

- Painel publicado: https://smartpark-sim.mateus-ro-fernandesescola.workers.dev/
- Projeto Wokwi: [MicroPython MQTT Weather Logger (ESP32) Copy - Wokwi ESP32, STM32, Arduino Simulator](https://wokwi.com/projects/481613529141121025)
- Video de demonstracao: [Projeto SmartPark - YouTube](https://youtu.be/WqgKUGeqIs8)

## Problema

Monitorar 3 vagas de estacionamento. Cada vaga tem um sensor ultrassonico HC-SR04.

- Grandeza: distancia (cm). Vaga ocupada se distancia < 20 cm.
- Intervalo de coleta: 2 s.
- Alerta: estacionamento lotado (3 vagas ocupadas).

## Arquitetura

```
HC-SR04 (x3) -> ESP32 (Wokwi) -> HTTPS POST -> Supabase Edge Function (API)
                                                   |
                                             Supabase (Postgres)
                                                   |
                       Painel (Cloudflare) <- HTTPS GET (latest / history)
```

## Estrutura

```
wokwi/      firmware do ESP32 (main.py), driver OLED, diagram.json e modelo de segredos
supabase/   schema.sql e Edge Function (functions/api/index.ts)
web/        painel (index.html)
```

## Como funciona

- **Sensor:** o ESP32 envia um pulso de 10 us no TRIG e mede a largura do pulso no ECHO. Converte para cm (us / 58), valida a faixa de 2 a 400 cm e confirma a mudanca de estado com 2 leituras seguidas (filtro).
- **API:** `POST` recebe as leituras (exige o cabecalho `x-device-key`). `GET ?r=latest` devolve a ultima leitura de cada vaga. `GET ?r=history&limit=N` devolve o historico.
- **Armazenamento:** tabela `leituras` no Supabase. Os dados sao gravados mesmo com o painel fechado.
- **Painel:** consulta a API a cada 3 s e mostra valor, unidade, horario da ultima atualizacao, historico e alerta. Se passar de 10 s sem leitura nova, mostra "dados desatualizados" e volta ao normal quando a transmissao retoma.

## Como reproduzir

1. **Supabase:** crie um projeto e rode `supabase/schema.sql` no SQL Editor.
2. **API:** em Edge Functions, crie a funcao `api` com o conteudo de `supabase/functions/api/index.ts`. Desligue "Verify JWT". Em Secrets, crie `DEVICE_KEY` com uma senha sua.
3. **Wokwi:** crie um projeto ESP32 MicroPython com `main.py`, `ssd1306.py` e `diagram.json`. Crie o arquivo `secrets.py` a partir de `wokwi/secrets.example.py`, com sua `API_URL` e `DEVICE_KEY`.
4. **Painel:** em `web/index.html`, troque a constante `API` pela URL da sua funcao e publique (Cloudflare ou outro).
5. Rode a simulacao. O terminal deve mostrar `[API] HTTP 200`.

Observacao: o Wi-Fi virtual do Wokwi pode falhar em algumas redes (faculdade, empresa). Se nao conectar, teste com o hotspot do celular.

## Seguranca

- Nenhum segredo esta no repositorio. `secrets.py` esta no `.gitignore`.
- `DEVICE_KEY` fica como secret da Edge Function e no `secrets.py` local do Wokwi.
- Todos os dados sao simulados.

## Limitacoes

- Dados simulados, sem ruido real de sensor.
- Autenticacao do dispositivo por chave simples e painel publico sem login.
- A API le dados com a chave de servico; nao ha limite de requisicoes.

## Contribuicoes

| Integrante | Contribuicao               |
| ---------- | -------------------------- |
| NOME 1     | Henrique Giaxa da Rocha    |
| NOME 2     | Mateus Rodrigues Fernandes |

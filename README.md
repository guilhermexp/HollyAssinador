# HollyAssinador Offline

Edição para testes em macOS do [HollyAssinador](https://github.com/HollyGM/HollyAssinador), derivada do commit `7ba9fa6`. Assina PDFs individualmente ou em lote com certificado A1 (PFX/P12) ou token A3 (PKCS#11). Usa PAdES com SHA-256 e oferece assinatura invisível ou carimbo visual no rodapé.

## Gerar e abrir o aplicativo

Use macOS com Python 3.11+ e Tkinter. O ambiente de referência é macOS em Apple Silicon com Python 3.12.

```bash
git clone https://github.com/guilhermexp/HollyAssinador.git
cd HollyAssinador
./build_macos.sh
open dist/HollyAssinadorOffline.app
```

A preparação pode acessar o índice de pacotes Python. O instalador exige wheels com versão e hash listados em `requirements.lock`. O build verifica a assinatura ad hoc do pacote e executa o autoteste. A assinatura ad hoc permite testar o aplicativo no Mac em que foi gerado. O pacote não é notarizado.

Para repetir a abertura pela árvore de desenvolvimento, execute `./run_dev.sh` após o build. O script usa o ambiente já preparado.

## Testar uma assinatura

1. Escolha um PDF fictício em uma pasta local privada fora de serviços de sincronização.
2. Para A1, selecione um PFX ou P12 de teste e digite a senha. Para A3, o aplicativo procura as identidades de assinatura que o macOS reconhece nos tokens conectados. Um único certificado já aparece selecionado. Se houver vários, escolha o titular na lista e digite o PIN. Clique em **Atualizar** se conectar ou trocar o token com o aplicativo aberto. **Configuração manual de driver PKCS#11** continua disponível para tokens que aparecem apenas no driver do fabricante. O programa abre uma sessão por lote.
3. Escolha a aparência e clique em **Assinar PDF**. A cópia assinada tem permissão de leitura e escrita apenas para o proprietário. Um arquivo de saída já existente exige confirmação na interface.

O PDF incorpora o certificado público do titular para permitir a verificação da assinatura. Isso pode identificar o titular a quem receber o documento. A hora do carimbo visual vem do Mac. Esta edição não consulta autoridades de carimbo do tempo ou de revogação e não verifica a cadeia ICP-Brasil.

## Proteções e testes

O processo aplica uma política de rede do macOS antes de carregar as bibliotecas de assinatura ou o driver do token. Se a política falhar, o programa encerra antes de pedir credenciais. O diagnóstico `probe_pkcs11.py` usa a mesma proteção. Consulte os limites em [SECURITY.md](SECURITY.md).

```bash
./dist/HollyAssinadorOffline.app/Contents/MacOS/HollyAssinadorOffline --self-test
.venv/bin/python -m unittest discover -s tests -t . -v
```

O autoteste confere o bloqueio TCP e UDP em IPv4 e IPv6, gera um A1 temporário, assina um PDF e verifica sua integridade. Para identificar os rótulos em um token de teste, use `.venv/bin/python probe_pkcs11.py "/caminho/para/modulo.dylib"`.

As preferências em `~/Library/Application Support/HollyAssinadorOffline/config.json` contêm apenas o tipo de certificado e a aparência. O fork não lê a configuração da versão original.

## Licença

[Apache 2.0](LICENSE). Créditos e dependências em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

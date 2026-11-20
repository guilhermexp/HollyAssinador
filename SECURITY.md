# Segurança da edição offline

O aplicativo e o utilitário de inspeção do token importam `offline.py` antes das bibliotecas de terceiros. O módulo ativa uma política Seatbelt do macOS que bloqueia operações diretas de rede, restringe o acesso ao serviço de DNS e desativa core dumps do processo. A inicialização depende da API de sandbox disponível no macOS. Se a política não puder ser aplicada, a execução termina.

## Tratamento das credenciais

- A busca de arquivos A1 consulta nomes e caminhos localmente. Para um A1 do Chaves, a busca consulta identidades sem interação e a assinatura usa uma referência à chave via Security.framework. O macOS gerencia a autorização.
- O A1 em arquivo é aberto em memória pelo pyHanko. O PFX e a senha entram no processo durante a assinatura. O Python não garante a limpeza física imediata de todas as cópias na memória.
- A busca automática consulta as identidades de tokens no Chaves com interação desativada, sem pedir PIN. Ao assinar, o aplicativo reconfirma o token e o certificado escolhidos e fornece o PIN a um contexto de autenticação local do macOS, invalidado no fim do lote. No modo manual A3, o PIN é entregue ao módulo PKCS#11 escolhido. O aplicativo não solicita a exportação da chave privada. Use o módulo oficial instalado pelo fabricante.
- O arquivo de preferências guarda apenas tipo e aparência. Os campos de senha e PIN são esvaziados quando a operação é iniciada. O PDF de saída herda o modo privado do arquivo temporário criado por `mkstemp`.
- O certificado público e os metadados de assinatura ficam no PDF final. A chave privada, o PIN e a senha não fazem parte do formato de saída.

## Limites do bloqueio

A política vale para o processo assinador. Um serviço do fabricante que já rode separadamente, a sincronização de arquivos pelo macOS ou outro programa da máquina têm permissões próprias. Para um ensaio que exija todo o equipamento offline, desconecte suas interfaces de rede e use uma pasta local. Um driver nativo carregado no processo precisa ser confiável.

O caminho de build baixa dependências com hashes verificados quando necessário. A abertura do aplicativo empacotado e o script de desenvolvimento não instalam pacotes.

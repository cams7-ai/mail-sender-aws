# Passo a passo para migrar o `mail-sender` para AWS com AWS SAM

Este roteiro assume que o Windows já possui:

- AWS CLI instalado e autenticado em um perfil local.
- AWS SAM CLI instalado.
- Região padrão do projeto: `us-east-2`.
- Projeto local: `<diretorio-local>\mail-sender-aws`.

## 1. Arquitetura alvo

Para este projeto, a arquitetura mais simples e barata para iniciar na AWS e:

```text
Cliente HTTP
  -> Amazon API Gateway HTTP API
  -> AWS Lambda Python 3.12
  -> Amazon SES
  -> Destinatario do e-mail
```

Por que este desenho:

- O `mail-sender` e apenas uma API pequena de envio de e-mail.
- Não precisa de servidor sempre ligado.
- Não precisa de EC2, ECS, Load Balancer, NAT Gateway ou VPC.
- Lambda + HTTP API + SES tende a ser o caminho mais simples para começar no Free Tier.
- SES elimina a necessidade de guardar senha SMTP do Gmail ou outro provedor.

## 2. Validar o ambiente local

No PowerShell, execute:

```powershell
aws --version
sam --version
aws sts get-caller-identity --profile <perfil-aws-local>
```

O último comando deve retornar a conta e o ARN do usuario/role autenticado.

## 3. Preparar o Amazon SES

No primeiro momento, use o SES em sandbox.

Crie uma identidade de e-mail para o remetente:

```powershell
aws sesv2 create-email-identity `
  --email-identity "<remetente-verificado@example.com>" `
  --region us-east-2 `
  --profile <perfil-aws-local>
```

Depois, confirme o e-mail clicando no link enviado pela AWS.

Valide a identidade:

```powershell
aws sesv2 get-email-identity `
  --email-identity "<remetente-verificado@example.com>" `
  --region us-east-2 `
  --profile <perfil-aws-local>
```

Enquanto a conta estiver no sandbox do SES:

- O remetente precisa estar verificado.
- Os destinatários também precisam estar verificados.
- Para enviar para qualquer destinatário real, solicite production access no SES.

## 4. Decidir a forma de adaptar o código

Existem dois caminhos possíveis.

### Opção recomendada: Lambda handler puro

Criar um handler Lambda simples que recebe o JSON do API Gateway, valida com Pydantic e chama um novo `SesEmailSender`.

Vantagens:

- Menos dependências.
- Menor pacote.
- Cold start mais leve.
- Mais simples para uma unica rota `POST /api/v1/mail/send`.

### Opção alternativa: manter FastAPI com Mangum

Adicionar `mangum` e expor a aplicação FastAPI dentro do Lambda.

Vantagens:

- Reaproveita melhor a API atual.
- Mantém `/docs`, `/redoc` e OpenAPI com menos mudanca.

Desvantagens:

- Mais dependência.
- Mais sobrecarga para uma API que tem apenas uma rota essencial.

Para este projeto, siga com a opção recomendada: handler Lambda puro.

## 5. Criar a estrutura SAM

Crie estes arquivos no projeto:

```text
template.yaml
samconfig.local.toml
src/lambda_handler.py
src/infrastructure/ses_email_sender.py
```

Atualize também:

```text
pyproject.toml
tests/
```

## 6. Declarar as dependências Python

O builder Python padrão do AWS SAM lê `src/requirements.txt`. Por isso, esse arquivo é a fonte única das dependências de runtime:

```text
boto3>=1.35
pydantic[email]>=2
```

O `pyproject.toml` mantém apenas os metadados do projeto, a configuração das ferramentas e as dependências de desenvolvimento:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-cov>=5",
]
```

Não repita as dependências de runtime em `[project.dependencies]`, pois isso criaria duas fontes que poderiam ficar fora de sincronia.

## 7. Criar o sender baseado em SES

Crie `src/infrastructure/ses_email_sender.py`.

Responsabilidade:

- Ler `SES_FROM` do ambiente.
- Criar um client `boto3.client("sesv2")`.
- Enviar e-mail com `send_email`.
- Usar `Content.Simple.Subject` e `Content.Simple.Body.Text` ou `Html`, conforme `message_type`.
- Deixar erros da AWS propagarem ou convertê-los para a exceção de domínio já usada pela aplicação.

Variáveis esperadas:

```text
SES_FROM=<remetente-verificado@example.com>
```

Não será mais necessário:

```text
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASSWORD
SMTP_USE_TLS
```

## 8. Criar o Lambda handler

Crie `src/lambda_handler.py`.

Responsabilidade:

- Receber o evento do API Gateway HTTP API.
- Aceitar apenas `POST /api/v1/mail/send`.
- Fazer parse do `body` JSON.
- Validar usando `EmailRequest`.
- Chamar `SendEmailUseCase(SesEmailSender()).execute(...)`.
- Retornar resposta no formato proxy do API Gateway:

```json
{
  "statusCode": 200,
  "headers": {
    "content-type": "application/json"
  },
  "body": "{\"message\":\"E-mail enviado com sucesso.\"}"
}
```

Pontos importantes:

- O `body` precisa ser ‘string’ JSON.
- Erros 422, 500 e 503 devem manter o formato atual:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Dados de entrada inválidos."
  }
}
```

## 9. Criar o `template.yaml`

Crie um template SAM com:

- Runtime `python3.12`.
- Handler `lambda_handler.handler`.
- API Gateway HTTP API.
- Variável `SES_FROM`.
- Permissão minima para `ses:SendEmail`.
- Logs com retenção curta para controlar custo.

Exemplo base:

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31
Description: mail-sender serverless API

Parameters:
  SesFrom:
    Type: String
    NoEcho: true
    Description: Email address verified in Amazon SES and used as the sender

Globals:
  Function:
    Runtime: python3.12
    Timeout: 10
    MemorySize: 128
    Architectures:
      - x86_64
    Environment:
      Variables:
        SES_FROM: !Ref SesFrom

Resources:
  MailSenderFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: lambda_handler.handler
      Policies:
        - Statement:
            - Effect: Allow
              Action:
                - ses:SendEmail
              Resource: "*"
      Events:
        SendMail:
          Type: HttpApi
          Properties:
            Path: /api/v1/mail/send
            Method: POST

Outputs:
  ApiUrl:
    Description: HTTP API endpoint
    Value: !Sub "https://${ServerlessHttpApi}.execute-api.${AWS::Region}.amazonaws.com"
```

Depois, restrinja o `Resource` da política SES para a identidade verificada quando confirmar o ARN correto.

O `samconfig.local.toml` é versionado como configuração-base e não deve conter perfil AWS, e-mail ou outros dados locais. Depois de clonar o projeto, copie-o para `samconfig.toml`:

```powershell
Copy-Item samconfig.local.toml samconfig.toml
```

O `samconfig.toml` está no `.gitignore` e é o arquivo privado usado automaticamente pelo SAM. Acrescente nele os valores locais:

```toml
[default.deploy.parameters]
profile = "<perfil-aws-local>"
parameter_overrides = "SesFrom=<remetente-verificado@example.com>"
```

Depois disso, execute o deploy normalmente:

```powershell
sam deploy
```

`NoEcho` reduz a exposição do valor em saídas e eventos do CloudFormation. Para desenvolvimento local, use `env.local.json`, que também está no `.gitignore`.

## 10. Testar localmente

Crie e ative o ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Instale dependências:

```powershell
python -m pip install -r src/requirements.txt
python -m pip install -e ".[dev]"
```

Execute os testes existentes:

```powershell
python -m pytest
```

Build com SAM:

```powershell
sam build
```

Teste local do endpoint:

```powershell
sam local start-api --env-vars env.local.json
```

Exemplo de `env.local.json`:

```json
{
  "MailSenderFunction": {
    "SES_FROM": "<remetente-verificado@example.com>"
  }
}
```

Chamada local:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:3000/api/v1/mail/send" `
  -ContentType "application/json" `
  -Body '{"to":"<destinatario-verificado@example.com>","subject":"Teste AWS","body":"Mensagem enviada via Lambda + SES"}'
```

Observação: para `sam local start-api`, pode ser necessário Docker ‘Desktop’ em execução.

## 11. Fazer o build e deploy

Execute:

```powershell
sam build
sam deploy
```

## 12. Testar a API publicada

Pegue a URL no output `ApiUrl`:

```powershell
aws cloudformation describe-stacks `
  --stack-name mail-sender `
  --region us-east-2 `
  --profile <perfil-aws-local> `
  --query "Stacks[0].Outputs"
```

Teste:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://<api-id>.execute-api.us-east-2.amazonaws.com/api/v1/mail/send" `
  -ContentType "application/json" `
  -Body '{"to":"<destinatario-verificado@example.com>","subject":"Teste AWS","body":"Mensagem enviada via AWS"}'
```

Se a conta SES ainda estiver em sandbox, use um destinatario tambem verificado.

## 13. Configurar segurança da API

Não deixe essa API publica sem algum controle.

Para o primeiro momento, escolha uma destas opções:

- API key simples no header, validada pelo próprio Lambda.
- JWT authorizer no HTTP API, se já houver provedor OIDC/Cognito.
- Lambda authorizer, se precisar de regra customizada.

Para uma versão inicial barata e simples, uma API key em variável de ambiente resolve:

```text
MAIL_SENDER_API_KEY=valor-longo-aleatorio
```

O Lambda deve exigir:

```text
x-api-key: valor-longo-aleatorio
```

## 14. Configurar logs e monitoramento

No CloudWatch Logs:

- Configure retenção curta, por exemplo, 7 ou 14 dias.
- Evite logar corpo completo de e-mail.
- Nunca logue credenciais, tokens ou headers sensíveis.

Alarmes mínimos:

- Erros da Lambda acima de zero.
- Throttles da Lambda acima de zero.
- Erros 5xx no API Gateway.

## 15. Configurar controle de custo

Como você pretende usar o plano gratuito, configure um Budget logo no início.

Crie um budget mensal pequeno, por exemplo, US$ 1 ou US$ 5:

```powershell
aws budgets create-budget `
  --account-id <ACCOUNT_ID> `
  --budget file://budget.json `
  --notifications-with-subscribers file://budget-notifications.json `
  --region us-east-1 `
  --profile <perfil-aws-local>
```

Observação: AWS Budgets usa endpoint em `us-east-1`.

Também acompanhe:

```powershell
aws freetier get-free-tier-usage --region us-east-1 --profile <perfil-aws-local>
```

## 16. Solicitar production access no SES

Quando o teste em sandbox estiver funcionando, solicite production access para remover as limitações de destinatário.

No pedido, informe:

- Tipo de e-mail enviado.
- Como os destinatários deram consentimento.
- Como você lidara com bounce e complaint.
- Volume esperado.
- Dominio/remetente usado.

Antes de produção, prefira verificar um domínio em vez de apenas um e-mail individual.

## 17. Checklist final

- `aws sts get-caller-identity` funcionando com o perfil AWS local.
- `sam --version` funcionando.
- Identidade SES verificada em `us-east-2`.
- `SesEmailSender` implementado.
- `lambda_handler.py` implementado.
- `template.yaml` criado.
- Testes unitários atualizados.
- `sam build` executando sem erro.
- `sam local start-api` validado.
- `sam deploy` concluído.
- Endpoint publicado testado.
- API protegida por chave/JWT/authorizer.
- Budget e alertas configurados.
- Logs sem dados sensíveis.
- Production access do SES solicitado quando necessário.

## 18. Rollback

Se precisar remover os recursos criados:

```powershell
sam delete --stack-name mail-sender --region us-east-2 --profile <perfil-aws-local>
```

Remova a identidade do SES:

```powershell
aws sesv2 delete-email-identity `
  --email-identity "<remetente-verificado@example.com>" `
  --region us-east-2 `
  --profile <perfil-aws-local>
```

Valide a identidade:

```powershell
aws sesv2 get-email-identity `
  --email-identity "<remetente-verificado@example.com>" `
  --region us-east-2 `
  --profile <perfil-aws-local>
```

Antes de remover, confirme que não ha dependências externas usando a API publicada.

## Referencias oficiais

- [AWS SAM CLI - Install](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- [AWS SAM - Deploying applications](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-deploying.html)
- [AWS SAM - AWS::Serverless::Function](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-function.html)
- [AWS Lambda with Python](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html)
- [Amazon SES setup](https://docs.aws.amazon.com/ses/latest/dg/setting-up.html)
- [Amazon SES identities](https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html)
- [Amazon SES API sending](https://docs.aws.amazon.com/ses/latest/dg/send-email-api.html)
- [Amazon SES production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html)

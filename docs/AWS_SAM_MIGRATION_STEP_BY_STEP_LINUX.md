# Migração do `mail-sender-aws` com AWS SAM no Linux

Este guia corresponde ao [`template.yaml`](../template.yaml) vigente. A função não possui API Gateway ou URL pública. O `loto-bot` a invoca diretamente com `lambda:InvokeFunction`.

## Arquitetura e segurança

Fluxo: `loto-bot` EC2 → Lambda Invoke autorizado por IAM → `MailSenderFunction` fora da VPC do cliente → Amazon SES.

- `MAIL_SENDER_URL` não é usado na AWS; o consumidor recebe o ARN em `MAIL_SENDER_FUNCTION_NAME`;
- não há `X-API-Key`, `INTEGRATION_API_TOKEN` ou segredo compartilhado;
- a role do `loto-bot` deve permitir invocação somente do ARN desta função;
- a função permite somente `ses:SendEmail`;
- não adicione evento HTTP público para esta integração;
- a função não precisa de VPC, NAT ou Security Group para chamar SES;
- a política SES limita o endereço de origem com `ses:FromAddress`; restrinja também o ARN da identidade após validar a identidade verificada.

## Pré-requisitos

- Linux com Python 3.12, AWS CLI v2 e AWS SAM CLI instalados;
- Docker Engine em execução para `sam local` (não é necessário para os passos de deploy abaixo);
- identidade AWS com acesso a CloudFormation, Lambda, IAM, Logs, S3 e SES;
- remetente verificado no SES;
- mesma conta e região usadas pelo `loto-bot`, salvo se políticas cross-account forem configuradas explicitamente.

Configure os valores para sua conta e região:

```bash
AWS_PROFILE="<perfil>"
AWS_REGION="us-east-1"
STACK_NAME="mail-sender"
SES_FROM="<remetente-verificado>"
```

Se a conta SES estiver em sandbox, remetentes e destinatários precisam estar verificados. Solicite saída do sandbox antes de uso real.

## Preparar o ambiente e validar

Na raiz do repositório:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r src/requirements.txt
python -m pip install -e '.[dev]'

python -m pytest
sam validate --lint --template-file template.yaml
sam build --template-file template.yaml
```

## Executar localmente com SAM

O `sam local start-api` usa Docker para simular a Lambda. Confirme que o Docker Engine está ativo e que `docker info` funciona. Crie `env.local.json` na raiz do repositório:

```json
{
  "MailSenderFunction": {
    "SES_FROM": "remetente-verificado@example.com"
  }
}
```

O arquivo `env.local.json` é ignorado pelo Git. Use um remetente verificado no SES na região configurada. A execução local pode acessar a AWS com as credenciais disponíveis no ambiente; uma chamada que envie e-mail usa SES real e pode consumir cota.

Inicie o endpoint local:

```bash
sam local start-api \
  --env-vars env.local.json \
  --region "$AWS_REGION"
```

Em outro terminal, chame o endpoint. Para um envio real, o destinatário também deve estar verificado enquanto a conta SES estiver no sandbox:

```bash
curl --fail-with-body \
  --request POST \
  --url http://127.0.0.1:3000/api/v1/mail/send \
  --header 'Content-Type: application/json' \
  --data '{"to":"destinatario-verificado@example.com","subject":"Teste local","body":"Mensagem enviada pelo SAM local","message_type":"TEXT"}'
```

O `sam local` é apenas para desenvolvimento: o endpoint local simula a integração HTTP e não publica API Gateway na AWS.

## Deploy

Revise os valores exportados antes de fazer o deploy. O parâmetro `SesFrom` usa `NoEcho`, mas ainda deve ser tratado como configuração sensível.

```bash
sam deploy \
  --template-file template.yaml \
  --stack-name "$STACK_NAME" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --parameter-overrides "SesFrom=$SES_FROM"
```

Revise o change set antes de confirmar.

## Entregar o ARN ao `loto-bot`

```bash
MAIL_SENDER_FUNCTION_ARN="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='FunctionArn'].OutputValue | [0]" \
  --output text \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE")"

printf '%s\n' "$MAIL_SENDER_FUNCTION_ARN"
```

Passe o valor como `MailSenderFunctionArn` no deploy do `loto-bot`. O bootstrap grava:

```text
MAIL_SENDER_FUNCTION_NAME=<FunctionArn>
```

O nome histórico `MAIL_SENDER_URL` não representa mais o contrato AWS e não deve ser configurado no ambiente implantado.

## Smoke test direto

O teste abaixo envia e-mail real e pode consumir cota do SES. Use um destinatário verificado quando a conta estiver no sandbox.

```bash
PAYLOAD='{"to":"destino@example.com","subject":"Teste","body":"Teste do mail-sender","message_type":"TEXT"}'
aws lambda invoke \
  --function-name "$MAIL_SENDER_FUNCTION_ARN" \
  --cli-binary-format raw-in-base64-out \
  --payload "$PAYLOAD" \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  response.json

cat response.json
```

A resposta da função mantém o formato `statusCode`/`body`; isso é contrato da aplicação, não indicação de exposição HTTP.

## Operação, atualização e rollback

```bash
FUNCTION_NAME="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='FunctionName'].OutputValue | [0]" \
  --output text \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE")"

aws logs tail "/aws/lambda/$FUNCTION_NAME" \
  --since 10m \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE"
```

Para atualizar, rode testes, `sam build` e `sam deploy`, sempre revisando o change set. Para rollback, faça deploy de uma revisão anterior do código/template. Não registre corpo, destinatário ou conteúdo sensível em logs.

## Checklist

- [ ] Remetente verificado e situação do sandbox conferida.
- [ ] Testes, `sam validate` e `sam build` aprovados.
- [ ] Nenhum evento API Gateway ou Function URL configurado.
- [ ] A função não possui `VpcConfig` nem `AWSLambdaVPCAccessExecutionRole`.
- [ ] Output `FunctionArn` entregue ao `loto-bot`.
- [ ] Role do consumidor limitada a este ARN.
- [ ] Nenhuma chave de API compartilhada configurada.
- [ ] Retenção de logs e orçamento revisados.

# Migração do `mail-sender-aws` com AWS SAM

Este guia corresponde ao [`template.yaml`](../template.yaml) vigente. A função não possui API Gateway ou URL pública. O `loto-bot` a invoca diretamente com `lambda:InvokeFunction`.

## Arquitetura e segurança

Fluxo: `loto-bot` EC2 → Lambda Invoke autorizado por IAM → `MailSenderFunction` fora da VPC do cliente → Amazon SES.

- `MAIL_SENDER_URL` não é usado na AWS; o consumidor recebe o ARN em `MAIL_SENDER_FUNCTION_NAME`;
- não há `X-API-Key`, `INTEGRATION_API_TOKEN` ou segredo compartilhado;
- a role do `loto-bot` deve permitir invocação somente do ARN desta função;
- a função permite somente `ses:SendEmail`;
- não adicione evento HTTP público para esta integração.
- a função não precisa de VPC, NAT ou Security Group para chamar SES.
- a política SES limita o endereço de origem com `ses:FromAddress`; restrinja também o ARN da identidade após validar a identidade verificada.

## Pré-requisitos

- AWS CLI e SAM CLI;
- Python 3.12;
- identidade AWS com acesso a CloudFormation, Lambda, IAM, Logs, S3 e SES;
- remetente verificado no SES;
- mesma conta e região usadas pelo `loto-bot`, salvo se políticas cross-account forem configuradas explicitamente.

```powershell
$AwsProfile = "<perfil>"
$AwsRegion = "us-east-1"
$StackName = "mail-sender"
$SesFrom = "<remetente-verificado>"
```

Se a conta SES estiver em sandbox, remetentes e destinatários precisam estar verificados. Solicite saída do sandbox antes de uso real.

## Testar e validar

```powershell
.venv\Scripts\python.exe -m pytest
sam validate --lint --template-file template.yaml
sam build --template-file template.yaml
```

## Deploy

```powershell
sam deploy `
  --template-file template.yaml `
  --stack-name $StackName `
  --resolve-s3 `
  --capabilities CAPABILITY_IAM `
  --region $AwsRegion `
  --profile $AwsProfile `
  --parameter-overrides SesFrom=$SesFrom
```

Revise o change set antes de confirmar. O parâmetro `SesFrom` usa `NoEcho`, mas ainda deve ser tratado como configuração sensível.

## Entregar o ARN ao `loto-bot`

```powershell
$MailSenderFunctionArn = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --query "Stacks[0].Outputs[?OutputKey=='FunctionArn'].OutputValue | [0]" `
  --output text --region $AwsRegion --profile $AwsProfile
```

Passe o valor como `MailSenderFunctionArn` no deploy do `loto-bot`. O bootstrap grava:

```text
MAIL_SENDER_FUNCTION_NAME=<FunctionArn>
```

O nome histórico `MAIL_SENDER_URL` não representa mais o contrato AWS e não deve ser configurado no ambiente implantado.

## Smoke test direto

O teste abaixo envia e-mail real e pode consumir cota do SES:

```powershell
$Payload = '{"to":"destino@example.com","subject":"Teste","body":"Teste do mail-sender","message_type":"TEXT"}'
aws lambda invoke `
  --function-name $MailSenderFunctionArn `
  --cli-binary-format raw-in-base64-out `
  --payload $Payload `
  --region $AwsRegion --profile $AwsProfile `
  response.json
Get-Content response.json
```

A resposta da função mantém o formato `statusCode`/`body`; isso é contrato da aplicação, não indicação de exposição HTTP.

## Operação, atualização e rollback

```powershell
$FunctionName = aws cloudformation describe-stacks --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='FunctionName'].OutputValue | [0]" --output text --region $AwsRegion --profile $AwsProfile
aws logs tail "/aws/lambda/$FunctionName" --since 10m --region $AwsRegion --profile $AwsProfile
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

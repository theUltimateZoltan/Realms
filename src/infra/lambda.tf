module "lambda_function" {
  for_each = toset(["interact", "spawn"])

  source = "terraform-aws-modules/lambda/aws"

  function_name = "realms_${each.key}"
  handler       = "${each.key}.lambda_handler"
  runtime       = "python3.8"
  source_path   = "logic"
  layers = [
    aws_lambda_layer_version.dependencies_layer.arn
  ]
}

data "aws_iam_policy_document" "lambda_access_to_dynamodb" {
  statement {
    effect = "Allow"
    actions = ["dynamodb:List*",
      "dynamodb:DescribeReservedCapacity*",
      "dynamodb:DescribeLimits",
      "dynamodb:DescribeTimeToLive"
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:BatchGet*",
      "dynamodb:DescribeStream",
      "dynamodb:DescribeTable",
      "dynamodb:Get*",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:BatchWrite*",
      "dynamodb:CreateTable",
      "dynamodb:Delete*",
      "dynamodb:Update*",
      "dynamodb:PutItem"
    ]
    resources = [
      module.dynamodb_table.dynamodb_table_arn
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "codecommit:GetFile",
      "codecommit:GetFolder"
    ]
    resources = [
      aws_codecommit_repository.realms_repo.arn
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "execute-api:Invoke",
      "execute-api:ManageConnections"
    ]
    resources = [
      "arn:aws:execute-api:${var.region}:${var.account}:${ aws_apigatewayv2_api.ws_messenger_api_gateway.id }/develop/POST/@connections/*"
    ]
  }
}

resource "aws_iam_policy" "lambda_iam_policy" {
  name        = "RealmsLambdaPolicy"
  description = "Realms interaction lambda function IAM policy"
  policy      = data.aws_iam_policy_document.lambda_access_to_dynamodb.json
}

resource "aws_iam_role_policy_attachment" "lambda_policy_attachement" {
  for_each = toset(["interact", "spawn"])
  role       = module.lambda_function[each.key].lambda_role_name
  policy_arn = aws_iam_policy.lambda_iam_policy.arn
}

resource "null_resource" "download_lambda_dependencies" {
  provisioner "local-exec" {
    command = "chmod +x scripts/build_lambda.sh && scripts/build_lambda.sh"
  }
}

resource "aws_lambda_layer_version" "dependencies_layer" {
  depends_on = [
    null_resource.download_lambda_dependencies
  ]

  filename   = "/tmp/lambda_layer_payload.zip"
  layer_name = "interaction_dependencies"

  compatible_runtimes = ["python3.8"]
}

resource "aws_cloudwatch_event_target" "spawn_event_target_executor" {
  arn  = module.lambda_function["spawn"].lambda_function_arn
  rule = aws_cloudwatch_event_rule.spawn_event_rule.id
}

resource "aws_cloudwatch_event_rule" "spawn_event_rule" {
  name = "spawn_event_rule"
  schedule_expression = "rate(1 minute)"
}

resource "aws_lambda_permission" "allow_cloudwatch_to_call_spawn" {
    statement_id = "AllowExecutionFromCloudWatch"
    action = "lambda:InvokeFunction"
    function_name = "${module.lambda_function["spawn"].lambda_function_name}"
    principal = "events.amazonaws.com"
    source_arn = "${aws_cloudwatch_event_rule.spawn_event_rule.arn}"
}
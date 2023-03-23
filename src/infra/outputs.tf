output "ws_api_url" {
  value = aws_apigatewayv2_stage.ws_messenger_api_stage.invoke_url
}

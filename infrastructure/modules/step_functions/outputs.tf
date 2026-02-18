output "state_machine_arn" {
  description = "ARN of the processing pipeline state machine"
  value       = aws_sfn_state_machine.processing_pipeline.arn
}

output "state_machine_name" {
  description = "Name of the processing pipeline state machine"
  value       = aws_sfn_state_machine.processing_pipeline.name
}

output "eventbridge_role_arn" {
  description = "ARN of the EventBridge IAM role"
  value       = aws_iam_role.eventbridge.arn
}

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
  value       = var.enable_s3_event_trigger ? aws_iam_role.eventbridge[0].arn : null
}

output "training_state_machine_arn" {
  description = "ARN of the training pipeline state machine"
  value       = var.enable_training_pipeline ? aws_sfn_state_machine.training_pipeline[0].arn : ""
}

output "training_state_machine_name" {
  description = "Name of the training pipeline state machine"
  value       = var.enable_training_pipeline ? aws_sfn_state_machine.training_pipeline[0].name : ""
}

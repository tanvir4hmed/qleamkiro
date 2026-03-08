variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "huggingface_inference_image" {
  description = "HuggingFace PyTorch inference container image URI"
  type        = string
  # Default: HF PyTorch inference CPU container for us-east-1
  default = "763104351884.dkr.ecr.us-east-1.amazonaws.com/huggingface-pytorch-inference:2.1.0-transformers4.37.0-cpu-py310-ubuntu22.04"
}

variable "sagemaker_memory_mb" {
  description = "Memory for SageMaker Serverless endpoint (MB)"
  type        = number
  default     = 4096
}

variable "sagemaker_max_concurrency" {
  description = "Max concurrent invocations for SageMaker Serverless"
  type        = number
  default     = 5
}

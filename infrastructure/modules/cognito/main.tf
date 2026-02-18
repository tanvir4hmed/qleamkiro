# =============================================================================
# Module: Cognito
# User Pool + App Client for parent authentication
# =============================================================================

resource "aws_cognito_user_pool" "main" {
  name = "${var.project}-${var.environment}-user-pool"

  # Username configuration
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Password policy
  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Email verification
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Qleam — Verify your email"
    email_message        = "Your Qleam verification code is {####}"
  }

  # User attributes
  schema {
    name                     = "email"
    attribute_data_type      = "String"
    required                 = true
    mutable                  = true
    string_attribute_constraints {
      min_length = 5
      max_length = 256
    }
  }

  schema {
    name                     = "given_name"
    attribute_data_type      = "String"
    required                 = false
    mutable                  = true
    string_attribute_constraints {
      min_length = 1
      max_length = 100
    }
  }

  # MFA configuration
  mfa_configuration = var.enable_mfa ? "OPTIONAL" : "OFF"

  dynamic "software_token_mfa_configuration" {
    for_each = var.enable_mfa ? [1] : []
    content {
      enabled = true
    }
  }

  # Admin create user config
  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  # User pool add-ons
  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }

  tags = {
    Name = "${var.project}-${var.environment}-user-pool"
  }
}

# -----------------------------------------------------------------------------
# User Pool Domain
# -----------------------------------------------------------------------------
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project}-${var.environment}-auth"
  user_pool_id = aws_cognito_user_pool.main.id
}

# -----------------------------------------------------------------------------
# App Client (for frontend)
# -----------------------------------------------------------------------------
resource "aws_cognito_user_pool_client" "frontend" {
  name         = "${var.project}-${var.environment}-frontend-client"
  user_pool_id = aws_cognito_user_pool.main.id

  # No client secret for SPA
  generate_secret = false

  # Token validity
  access_token_validity  = 1   # hours
  id_token_validity      = 1   # hours
  refresh_token_validity = 30  # days

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # Auth flows
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH"
  ]

  # OAuth settings
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["email", "openid", "profile"]

  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  supported_identity_providers = ["COGNITO"]

  # Prevent user existence errors
  prevent_user_existence_errors = "ENABLED"

  # Read/write attributes
  read_attributes  = ["email", "given_name", "email_verified"]
  write_attributes = ["email", "given_name"]
}

# -----------------------------------------------------------------------------
# Identity Pool (for AWS resource access from frontend)
# -----------------------------------------------------------------------------
resource "aws_cognito_identity_pool" "main" {
  identity_pool_name               = "${var.project}-${var.environment}-identity-pool"
  allow_unauthenticated_identities = false

  cognito_identity_providers {
    client_id               = aws_cognito_user_pool_client.frontend.id
    provider_name           = aws_cognito_user_pool.main.endpoint
    server_side_token_check = true
  }
}

# Identity Pool Roles
resource "aws_cognito_identity_pool_roles_attachment" "main" {
  identity_pool_id = aws_cognito_identity_pool.main.id

  roles = {
    "authenticated" = var.cognito_auth_role_arn
  }
}

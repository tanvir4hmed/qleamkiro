/**
 * Qleam — AWS Amplify Configuration
 * Values injected at build time from environment variables or Terraform outputs
 */
const awsConfig = {
  Auth: {
    Cognito: {
      userPoolId: process.env.REACT_APP_COGNITO_USER_POOL_ID || '',
      userPoolClientId: process.env.REACT_APP_COGNITO_CLIENT_ID || '',
      loginWith: {
        email: true,
      },
    },
  },
};

export const API_BASE_URL = process.env.REACT_APP_API_URL || '';

export default awsConfig;

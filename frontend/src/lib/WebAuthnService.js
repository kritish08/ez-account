/**
 * Utility to handle WebAuthn (Passkey) browser APIs.
 * It manages the conversion between backend-friendly formats (JSON/Base64) 
 * and browser-required binary formats (ArrayBuffer/Uint8Array).
 */

const base64ToBuffer = (base64) => {
  const binaryString = window.atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
};

const bufferToBase64 = (buffer) => {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
};

// Deeply search and convert ArrayBuffers to Base64 (for sending assertions back to server)
const recursiveBufferToBase64 = (obj) => {
  if (obj instanceof ArrayBuffer || obj instanceof Uint8Array) {
    return bufferToBase64(obj);
  }
  if (Array.isArray(obj)) {
    return obj.map(recursiveBufferToBase64);
  }
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj).map(([k, v]) => [k, recursiveBufferToBase64(v)])
    );
  }
  return obj;
};

export const WebAuthnService = {
  /**
   * registrationOptions: The response from /auth/passkey/register/begin
   */
  async register(registrationOptions) {
    // 1. Prepare options (convert Base64 strings to ArrayBuffers)
    const options = {
      publicKey: {
        ...registrationOptions.publicKey,
        challenge: base64ToBuffer(registrationOptions.publicKey.challenge),
        user: {
          ...registrationOptions.publicKey.user,
          id: base64ToBuffer(registrationOptions.publicKey.user.id),
        },
        // If there are existing credentials to exclude, convert them too
        excludeCredentials: (registrationOptions.publicKey.excludeCredentials || []).map(cred => ({
          ...cred,
          id: base64ToBuffer(cred.id),
        })),
      }
    };

    // 2. Trigger browser biometric prompt
    const credential = await navigator.credentials.create(options);

    // 3. Extract and format response for server
    return {
      id: credential.id,
      rawId: bufferToBase64(credential.rawId),
      type: credential.type,
      response: {
        attestationObject: bufferToBase64(credential.response.attestationObject),
        clientDataJSON: bufferToBase64(credential.response.clientDataJSON),
        // Some devices might provide transports
        transports: credential.response.getTransports ? credential.response.getTransports() : [],
      },
    };
  },

  /**
   * authenticationOptions: The response from /auth/passkey/authenticate/begin
   */
  async authenticate(authenticationOptions) {
    // 1. Prepare options
    const options = {
      publicKey: {
        ...authenticationOptions.publicKey,
        challenge: base64ToBuffer(authenticationOptions.publicKey.challenge),
        allowCredentials: (authenticationOptions.publicKey.allowCredentials || []).map(cred => ({
          ...cred,
          id: base64ToBuffer(cred.id),
        })),
      }
    };

    // 2. Trigger browser biometric prompt
    const assertion = await navigator.credentials.get(options);

    // 3. Format for server
    return {
      id: assertion.id,
      rawId: bufferToBase64(assertion.rawId),
      type: assertion.type,
      response: {
        authenticatorData: bufferToBase64(assertion.response.authenticatorData),
        clientDataJSON: bufferToBase64(assertion.response.clientDataJSON),
        signature: bufferToBase64(assertion.response.signature),
        userHandle: assertion.response.userHandle ? bufferToBase64(assertion.response.userHandle) : null,
      },
    };
  },

  isSupported() {
    return !!(window.PublicKeyCredential && 
              window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable &&
              window.PublicKeyCredential.isConditionalMediationAvailable);
  }
};

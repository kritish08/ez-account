import json
from fido2.server import Fido2Server
from fido2.webauthn import RegistrationResponse
from fido2.features import webauthn_json_mapping

webauthn_json_mapping.enabled = True

test_data = {
    'id': 'dGVzdF9pZA',
    'rawId': 'dGVzdF9pZA',
    'type': 'public-key',
    'response': {
        'attestationObject': 'o2NmbXRkbm9uZWdhdXRoRGF0YVjEc3AEXg3Xm-x1PqT4kYntP4T7C_0Gv26b9lOR9O2T474BAAAAAwAAAAAAAAAAAAAAAAAAAAAAMN0w3vWlTYOh-P864zT5NQEABwYgJ4I9m3XfA8C16wZ4n_N61sVn6XW33_7kQQM3A3wQn_AiWCAv0eT1-H_999K58J0-X2gE95Kqw9rI3a5oZ8A4Xz9u_qNzaWdYEGAjXhTjG7F4y5QzjWvBfL-FvO-m1x2C6C2t8uP6S0M3n7b7x_wDfwvPjF-6I2a0Zp2t9b0yMw4E-O6VvT2jXQ',
        'clientDataJSON': 'eyJ0eXBlIjoid2ViYXV0aG4uY3JlYXRlIiwiY2hhbGxlbmdlIjoiYWJjIiwib3JpZ2luIjoiaHR0cDovL2xvY2FsaG9zdDozMDAwIn0',
        'transports': []
    }
}
try:
    reg_response = RegistrationResponse.from_dict(test_data)
    print('SUCCESS:', reg_response)
except Exception as e:
    import traceback
    traceback.print_exc()

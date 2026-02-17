import requests
import sys
import json
from datetime import datetime

class EZAccountsAPITester:
    def __init__(self, base_url = "http://localhost:8000"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Test data
        self.test_user_email = f"test_{datetime.now().strftime('%H%M%S')}@example.com"
        self.test_user_password = "test123456"
        self.test_user_name = "Test User"
        
        # IDs for created entities
        self.customer_id = None
        self.invoice_id = None
        self.payment_id = None
        self.expense_id = None

    def log_result(self, test_name, success, details=""):
        """Log test result"""
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
        
    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=30)

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                print(f"✅ PASSED - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    self.log_result(name, True, f"Status: {response.status_code}")
                    return True, response_data
                except:
                    self.log_result(name, True, f"Status: {response.status_code}, No JSON response")
                    return True, {}
            else:
                print(f"❌ FAILED - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                    self.log_result(name, False, f"Status: {response.status_code}, Error: {error_data}")
                except:
                    print(f"   Response: {response.text}")
                    self.log_result(name, False, f"Status: {response.status_code}, Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ FAILED - Exception: {str(e)}")
            self.log_result(name, False, f"Exception: {str(e)}")
            return False, {}

    def test_user_registration(self):
        """Test user registration"""
        success, response = self.run_test(
            "User Registration",
            "POST",
            "auth/register",
            200,
            data={
                "email": self.test_user_email,
                "password": self.test_user_password,
                "name": self.test_user_name
            }
        )
        
        if success and 'access_token' in response:
            self.token = response['access_token']
            print(f"   ✅ Token received: {self.token[:20]}...")
            return True
        return False

    def test_user_login(self):
        """Test user login"""
        success, response = self.run_test(
            "User Login",
            "POST",
            "auth/login",
            200,
            data={
                "email": self.test_user_email,
                "password": self.test_user_password
            }
        )
        
        if success and 'access_token' in response:
            self.token = response['access_token']
            print(f"   ✅ Login successful, token: {self.token[:20]}...")
            return True
        return False

    def test_get_user_profile(self):
        """Test get current user profile"""
        success, response = self.run_test(
            "Get User Profile",
            "GET",
            "auth/me",
            200
        )
        
        if success and 'email' in response:
            print(f"   ✅ User profile: {response['name']} ({response['email']})")
            return True
        return False

    def test_business_setup(self):
        """Test business setup"""
        success, response = self.run_test(
            "Business Setup",
            "POST",
            "business/setup",
            200,
            data={
                "name": "Test Business Ltd",
                "address": "123 Test Street, Test City",
                "phone": "+91 98765 43210",
                "email": "business@test.com",
                "gstin": "29ABCDE1234F1Z5",
                "financial_year_start": "April",
                "opening_cash": 10000.0,
                "opening_bank": 50000.0
            }
        )
        
        if success:
            print(f"   ✅ Business setup completed")
            return True
        return False

    def test_get_business(self):
        """Test get business details"""
        success, response = self.run_test(
            "Get Business Details",
            "GET",
            "business",
            200
        )
        
        if success and 'name' in response:
            print(f"   ✅ Business: {response['name']}")
            return True
        return False

    def test_create_customer(self):
        """Test customer creation"""
        success, response = self.run_test(
            "Create Customer",
            "POST",
            "customers",
            200,
            data={
                "name": "Test Customer",
                "phone": "+91 87654 32109",
                "address": "456 Customer Street",
                "gstin": "29XYZTE5678G2A1",
                "opening_balance": 5000.0,
                "balance_type": "debit"
            }
        )
        
        if success and 'id' in response:
            self.customer_id = response['id']
            print(f"   ✅ Customer created with ID: {self.customer_id}")
            return True
        return False

    def test_list_customers(self):
        """Test list customers"""
        success, response = self.run_test(
            "List Customers",
            "GET",
            "customers",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✅ Found {len(response)} customers")
            return True
        return False

    def test_get_customer(self):
        """Test get specific customer"""
        if not self.customer_id:
            print("   ⚠️  Skipping - No customer ID available")
            return False
            
        success, response = self.run_test(
            "Get Customer Details",
            "GET",
            f"customers/{self.customer_id}",
            200
        )
        
        if success and 'name' in response:
            print(f"   ✅ Customer: {response['name']}, Outstanding: {response.get('outstanding', 0)}")
            return True
        return False

    def test_create_invoice(self):
        """Test invoice creation"""
        if not self.customer_id:
            print("   ⚠️  Skipping - No customer ID available")
            return False
            
        success, response = self.run_test(
            "Create Invoice",
            "POST",
            "invoices",
            200,
            data={
                "customer_id": self.customer_id,
                "items": [
                    {
                        "description": "Test Product 1",
                        "quantity": 2,
                        "rate": 100.0
                    },
                    {
                        "description": "Test Product 2", 
                        "quantity": 1,
                        "rate": 150.0
                    }
                ],
                "notes": "Test invoice for API testing",
                "date": datetime.now().strftime("%Y-%m-%d")
            }
        )
        
        if success and 'id' in response:
            self.invoice_id = response['id']
            print(f"   ✅ Invoice created: {response.get('invoice_number')} (ID: {self.invoice_id})")
            return True
        return False

    def test_list_invoices(self):
        """Test list invoices"""
        success, response = self.run_test(
            "List Invoices",
            "GET",
            "invoices",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✅ Found {len(response)} invoices")
            return True
        return False

    def test_get_invoice(self):
        """Test get specific invoice"""
        if not self.invoice_id:
            print("   ⚠️  Skipping - No invoice ID available")
            return False
            
        success, response = self.run_test(
            "Get Invoice Details",
            "GET",
            f"invoices/{self.invoice_id}",
            200
        )
        
        if success and 'invoice_number' in response:
            print(f"   ✅ Invoice: {response['invoice_number']}, Total: ₹{response['total']}")
            return True
        return False

    def test_invoice_pdf(self):
        """Test invoice PDF download"""
        if not self.invoice_id:
            print("   ⚠️  Skipping - No invoice ID available")
            return False
            
        url = f"{self.base_url}/api/invoices/{self.invoice_id}/pdf"
        headers = {'Authorization': f'Bearer {self.token}'}
        
        print(f"\n🔍 Testing Invoice PDF Download...")
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            success = response.status_code == 200 and response.headers.get('content-type') == 'application/pdf'
            
            if success:
                self.tests_passed += 1
                print(f"✅ PASSED - PDF generated, size: {len(response.content)} bytes")
                self.log_result("Invoice PDF Download", True, f"PDF size: {len(response.content)} bytes")
                return True
            else:
                print(f"❌ FAILED - Status: {response.status_code}, Content-Type: {response.headers.get('content-type')}")
                self.log_result("Invoice PDF Download", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ FAILED - Exception: {str(e)}")
            self.log_result("Invoice PDF Download", False, f"Exception: {str(e)}")
            return False
        finally:
            self.tests_run += 1

    def test_record_payment(self):
        """Test payment recording"""
        if not self.customer_id:
            print("   ⚠️  Skipping - No customer ID available")
            return False
            
        success, response = self.run_test(
            "Record Payment",
            "POST",
            "payments",
            200,
            data={
                "customer_id": self.customer_id,
                "amount": 200.0,
                "mode": "cash",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "notes": "Test payment via API"
            }
        )
        
        if success and 'id' in response:
            self.payment_id = response['id']
            print(f"   ✅ Payment recorded (ID: {self.payment_id})")
            if response.get('excess_as_credit', 0) > 0:
                print(f"   💰 Excess as credit: ₹{response['excess_as_credit']}")
            return True
        return False

    def test_list_payments(self):
        """Test list payments"""
        success, response = self.run_test(
            "List Payments",
            "GET",
            "payments",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✅ Found {len(response)} payments")
            return True
        return False

    def test_create_expense(self):
        """Test expense creation"""
        success, response = self.run_test(
            "Create Expense",
            "POST",
            "expenses",
            200,
            data={
                "description": "Office supplies for testing",
                "amount": 500.0,
                "mode": "bank",
                "category": "Office Supplies",
                "date": datetime.now().strftime("%Y-%m-%d")
            }
        )
        
        if success and 'id' in response:
            self.expense_id = response['id']
            print(f"   ✅ Expense recorded (ID: {self.expense_id})")
            return True
        return False

    def test_list_expenses(self):
        """Test list expenses"""
        success, response = self.run_test(
            "List Expenses",
            "GET",
            "expenses",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✅ Found {len(response)} expenses")
            return True
        return False

    def test_dashboard(self):
        """Test dashboard data"""
        success, response = self.run_test(
            "Get Dashboard",
            "GET",
            "dashboard",
            200
        )
        
        if success and 'cash_balance' in response:
            print(f"   ✅ Dashboard data - Cash: ₹{response['cash_balance']}, Bank: ₹{response['bank_balance']}")
            print(f"      Outstanding: ₹{response['total_outstanding']}, Credit: ₹{response['total_credit']}")
            return True
        return False

    def test_reports(self):
        """Test all report endpoints"""
        reports = [
            ("Outstanding Report", "reports/outstanding"),
            ("Credit Report", "reports/credit"),
            ("Sales Report", "reports/sales"),
            ("Expenses Report", "reports/expenses"),
            ("Cash/Bank Report", "reports/cash-bank")
        ]
        
        all_passed = True
        for report_name, endpoint in reports:
            success, response = self.run_test(
                report_name,
                "GET",
                endpoint,
                200
            )
            
            if success:
                if 'report' in response:
                    print(f"   ✅ {report_name}: {len(response['report'])} items")
                elif 'invoices' in response:
                    print(f"   ✅ {report_name}: {len(response['invoices'])} invoices")
                elif 'expenses' in response:
                    print(f"   ✅ {report_name}: {len(response['expenses'])} expenses")
                else:
                    print(f"   ✅ {report_name}: Data received")
            else:
                all_passed = False
                
        return all_passed

    def run_all_tests(self):
        """Run all API tests in sequence"""
        print("🚀 Starting EZ Accounts API Testing...")
        print(f"📍 Base URL: {self.base_url}")
        print("=" * 60)
        
        # Authentication tests
        print("\n📋 AUTHENTICATION TESTS")
        if not self.test_user_registration():
            print("❌ Registration failed - stopping tests")
            return False
            
        if not self.test_user_login():
            print("❌ Login failed - stopping tests") 
            return False
            
        self.test_get_user_profile()
        
        # Business setup tests
        print("\n🏢 BUSINESS SETUP TESTS")
        self.test_business_setup()
        self.test_get_business()
        
        # Customer tests
        print("\n👥 CUSTOMER TESTS")
        self.test_create_customer()
        self.test_list_customers()
        self.test_get_customer()
        
        # Invoice tests
        print("\n📄 INVOICE TESTS")
        self.test_create_invoice()
        self.test_list_invoices()
        self.test_get_invoice()
        self.test_invoice_pdf()
        
        # Payment tests
        print("\n💳 PAYMENT TESTS")
        self.test_record_payment()
        self.test_list_payments()
        
        # Expense tests
        print("\n💰 EXPENSE TESTS")
        self.test_create_expense()
        self.test_list_expenses()
        
        # Dashboard and reports
        print("\n📊 DASHBOARD & REPORTS TESTS")
        self.test_dashboard()
        self.test_reports()
        
        return True

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%")
        
        # Print failed tests
        failed_tests = [r for r in self.test_results if not r['success']]
        if failed_tests:
            print(f"\n❌ FAILED TESTS ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"   • {test['test']}: {test['details']}")
        
        print("\n✅ Test completed!")
        return self.tests_passed == self.tests_run

def main():
    """Main test function"""
    tester = EZAccountsAPITester()
    
    try:
        success = tester.run_all_tests()
        tester.print_summary()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        tester.print_summary()
        return 1
    except Exception as e:
        print(f"\n💥 Unexpected error: {str(e)}")
        tester.print_summary()
        return 1

if __name__ == "__main__":
    sys.exit(main())
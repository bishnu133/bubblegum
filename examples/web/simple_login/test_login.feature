Feature: Web login validation
  As a tester
  I want to validate login
  So that I can confirm basic access works

  Scenario: Successful login shows dashboard message
    Given I open the login page
    When I enter username "test.user@example.com"
    And I enter password "replace-with-secure-test-password"
    And I click the login button
    Then I should see "Welcome" on the dashboard

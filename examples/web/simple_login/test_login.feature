Feature: Real web login validation
  As a tester
  I want to validate Bubblegum on a public demo login app
  So that I can confirm real local web behavior before mobile/cloud trials

  Scenario: Valid login succeeds
    Given I open "/login"
    When I enter "tomsmith" into "Username"
    And I enter "SuperSecretPassword!" into "Password"
    And I click "Login"
    Then I should see "You logged into a secure area!"

  Scenario: Invalid login shows error
    Given I open "/login"
    When I enter "invalid-user" into "Username"
    And I enter "invalid-pass" into "Password"
    And I click "Login"
    Then I should see "Your username is invalid!"

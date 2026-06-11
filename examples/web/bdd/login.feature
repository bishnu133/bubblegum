Feature: Acme Notes login (Bubblegum BDD)
  Manual-QA-friendly Given/When/Then written in plain English on top of the
  Bubblegum natural-language engine. The When/Then steps are provided by
  `bubblegum.bdd.steps`; the Given (navigation) is provided by the test module.

  Scenario: Successful login lands on the dashboard
    Given I am on the login page
    When I enter "tester" into "Username"
    And I enter "bubblegum!" into "Password"
    And I click "Sign in"
    Then I should see "Dashboard"
    And I should see "Welcome back, tester."

  Scenario: Wrong password shows an error
    Given I am on the login page
    When I enter "tester" into "Username"
    And I enter "nope" into "Password"
    And I click "Sign in"
    Then I should see "Invalid username or password."

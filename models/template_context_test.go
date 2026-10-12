package models

import (
	check "gopkg.in/check.v1"
)

type mockTemplateContext struct {
	URL         string
	FromAddress string
}

func (m mockTemplateContext) getFromAddress() string {
	return m.FromAddress
}

func (m mockTemplateContext) getBaseURL() string {
	return m.URL
}

func (s *ModelsSuite) TestNewTemplateContext(c *check.C) {
	r := Result{
		BaseRecipient: BaseRecipient{
			FirstName: "Foo",
			LastName:  "Bar",
			Email:     "foo@bar.com",
		},
		RId: "1234567",
	}
	ctx := mockTemplateContext{
		URL:         "http://example.com",
		FromAddress: "From Address <from@example.com>",
	}
	expected := PhishingTemplateContext{
		URL:           ctx.URL,
		BaseURL:       ctx.URL,
		BaseRecipient: r.BaseRecipient,
		TrackingURL:   ctx.URL,
		Tracker:       "",
		From:          "From Address",
		RId:           r.RId,
	}
	got, err := NewPhishingTemplateContext(ctx, r.BaseRecipient, r.RId)
	c.Assert(err, check.Equals, nil)
	c.Assert(got, check.DeepEquals, expected)
}

func (s *ModelsSuite) TestExecuteTemplateHelpersAndSpintax(c *check.C) {
	r := BaseRecipient{
		FirstName: "sarah",
		LastName:  "connor",
		Email:     "sarah@acme.com",
		Company:   "Acme Technologies LLC",
	}

	// Test 1: Helper functions (title, companyClean)
	tmpl1 := "Hello {{.FirstName | title}}, hope all is well at {{.Company | companyClean}}."
	out1, err := ExecuteTemplate(tmpl1, r)
	c.Assert(err, check.Equals, nil)
	c.Assert(out1, check.Equals, "Hello Sarah, hope all is well at Acme Technologies.")

	// Test 2: Default fallback when FirstName is empty
	emptyR := BaseRecipient{
		Email: "info@acme.com",
	}
	tmpl2 := "Hi {{.FirstName | default \"there\"}}, reaching out from London."
	out2, err := ExecuteTemplate(tmpl2, emptyR)
	c.Assert(err, check.Equals, nil)
	c.Assert(out2, check.Equals, "Hi there, reaching out from London.")

	// Test 3: Salutation grammar cleanup when variable is empty
	tmpl3 := "Hi {{.FirstName}}, I saw your work."
	out3, err := ExecuteTemplate(tmpl3, emptyR)
	c.Assert(err, check.Equals, nil)
	c.Assert(out3, check.Equals, "Hi, I saw your work.")

	// Test 4: Spintax resolution
	tmpl4 := "{Hi|Hello|Hey} team"
	out4, err := ExecuteTemplate(tmpl4, r)
	c.Assert(err, check.Equals, nil)
	valid := (out4 == "Hi team" || out4 == "Hello team" || out4 == "Hey team")
	c.Assert(valid, check.Equals, true)
}

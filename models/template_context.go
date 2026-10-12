package models

import (
	"bytes"
	"fmt"
	"math/rand"
	"net/mail"
	"net/url"
	"regexp"
	"strings"
	"text/template"
	"time"
)

var (
	reSpintax    = regexp.MustCompile(`\{([^{}]+)\}`)
	reSpacePunct = regexp.MustCompile(`\s+([,.\?!;:])`)
	reHiSpace    = regexp.MustCompile(`(?i)\b(hi|hello|hey|dear)\s+([,.\?!])`)
	reZeroWidth  = regexp.MustCompile("[\u200B\u200C\u200D\uFEFF\u00AD\u200E\u200F\u202A-\u202E]")
)

// StripZeroWidthChars removes hidden Unicode zero-width/bidi control characters
// that trigger anti-evasion spam filters in Microsoft SmartScreen and Gmail.
func StripZeroWidthChars(s string) string {
	return reZeroWidth.ReplaceAllString(s, "")
}

// CleanCompanySuffixes strips legal business suffixes like "LLC", "Inc.", "Corp.",
// "Ltd." so emails read naturally like a real human wrote them (e.g. "Acme" instead of "Acme Inc.").
func CleanCompanySuffixes(s string) string {
	s = strings.TrimSpace(s)
	re := regexp.MustCompile(`(?i)\s*,?\s*\b(inc\.?|llc\.?|ltd\.?|corp\.?|corporation|gmbh|co\.?|holdings|group)\b\.?`)
	cleaned := strings.TrimSpace(re.ReplaceAllString(s, ""))
	if cleaned != "" {
		return cleaned
	}
	return s
}

// GetNaturalGreeting returns a context-aware human greeting
func GetNaturalGreeting() string {
	hour := time.Now().Hour()
	switch {
	case hour >= 5 && hour < 12:
		return "Good morning"
	case hour >= 12 && hour < 17:
		return "Good afternoon"
	case hour >= 17 && hour < 22:
		return "Good evening"
	default:
		greetings := []string{"Hello", "Hi"}
		return greetings[rand.Intn(len(greetings))]
	}
}

// templateFuncMap provides robust helper functions for natural email personalization.
var templateFuncMap = template.FuncMap{
	"default": func(defaultValue string, value interface{}) string {
		if value == nil {
			return defaultValue
		}
		str := strings.TrimSpace(fmt.Sprintf("%v", value))
		if str == "" || str == "<nil>" {
			return defaultValue
		}
		return str
	},
	"fallback": func(defaultValue string, value interface{}) string {
		if value == nil {
			return defaultValue
		}
		str := strings.TrimSpace(fmt.Sprintf("%v", value))
		if str == "" || str == "<nil>" {
			return defaultValue
		}
		return str
	},
	"firstOr": func(defaultValue string, value interface{}) string {
		if value == nil {
			return defaultValue
		}
		str := strings.TrimSpace(fmt.Sprintf("%v", value))
		if str == "" || str == "<nil>" {
			return defaultValue
		}
		fields := strings.Fields(str)
		if len(fields) > 0 {
			return fields[0]
		}
		return defaultValue
	},
	"greeting": func() string {
		options := []string{"Hi", "Hello", "Hey"}
		return options[rand.Intn(len(options))]
	},
	"timeGreeting": func() string {
		return GetNaturalGreeting()
	},
	"title": func(s interface{}) string {
		if s == nil {
			return ""
		}
		str := strings.TrimSpace(fmt.Sprintf("%v", s))
		if str == "" {
			return ""
		}
		words := strings.Fields(strings.ToLower(str))
		for i, w := range words {
			if len(w) > 0 {
				words[i] = strings.ToUpper(w[:1]) + w[1:]
			}
		}
		return strings.Join(words, " ")
	},
	"lower": func(s interface{}) string {
		if s == nil {
			return ""
		}
		return strings.ToLower(fmt.Sprintf("%v", s))
	},
	"upper": func(s interface{}) string {
		if s == nil {
			return ""
		}
		return strings.ToUpper(fmt.Sprintf("%v", s))
	},
	"firstWord": func(s interface{}) string {
		if s == nil {
			return ""
		}
		fields := strings.Fields(fmt.Sprintf("%v", s))
		if len(fields) > 0 {
			return fields[0]
		}
		return ""
	},
	"companyClean": func(s interface{}) string {
		if s == nil {
			return ""
		}
		return CleanCompanySuffixes(fmt.Sprintf("%v", s))
	},
}

// ProcessSpintax parses {option1|option2|option3} syntax and randomly selects
// an option, creating natural lexical variation across sent emails to prevent
// identical content fingerprinting by spam filters. Single braces without pipe
// (like JSON/CSS) are left completely untouched.
func ProcessSpintax(s string) string {
	for reSpintax.MatchString(s) {
		s = reSpintax.ReplaceAllStringFunc(s, func(match string) string {
			content := match[1 : len(match)-1]
			if !strings.Contains(content, "|") {
				return match
			}
			choices := strings.Split(content, "|")
			if len(choices) == 0 {
				return match
			}
			return choices[rand.Intn(len(choices))]
		})
		// Avoid infinite loops if no pipes remain
		if !strings.Contains(s, "|") {
			break
		}
	}
	return s
}

// CleanGrammarArtifacts automatically eliminates awkward template artifacts like
// "Hi ," or "Hey !" or double spaces before punctuation caused by missing fields.
func CleanGrammarArtifacts(s string) string {
	// Fix "Hi ," -> "Hi," or "Hello !" -> "Hello!"
	s = reHiSpace.ReplaceAllString(s, "$1$2")
	// Fix "word ," -> "word,"
	s = reSpacePunct.ReplaceAllString(s, "$1")
	return s
}

// CleanTypography ensures plain-text ASCII formatting: converts em-dashes (—) and en-dashes (–)
// to standard hyphens (-), curved quotes to plain quotes, and strips AI slop markers.
func CleanTypography(s string) string {
	s = strings.ReplaceAll(s, "—", " - ")
	s = strings.ReplaceAll(s, "–", "-")
	s = strings.ReplaceAll(s, "“", "\"")
	s = strings.ReplaceAll(s, "”", "\"")
	s = strings.ReplaceAll(s, "‘", "'")
	s = strings.ReplaceAll(s, "’", "'")
	s = strings.ReplaceAll(s, "…", "...")
	return s
}

// ExecuteTemplate creates a templated string based on the provided
// template body and data, evaluates helper functions, Spintax expressions,
// and normalizes template punctuation.
func ExecuteTemplate(text string, data interface{}) (string, error) {
	text = StripZeroWidthChars(text)
	text = CleanTypography(text)
	buff := bytes.Buffer{}
	tmpl, err := template.New("template").Funcs(templateFuncMap).Parse(text)
	if err != nil {
		return buff.String(), err
	}
	err = tmpl.Execute(&buff, data)
	if err != nil {
		return buff.String(), err
	}
	result := ProcessSpintax(buff.String())
	result = CleanGrammarArtifacts(result)
	result = StripZeroWidthChars(result)
	result = CleanTypography(result)
	return result, nil
}

// TemplateContext is an interface that allows both campaigns and email
// requests to have a PhishingTemplateContext generated for them.
type TemplateContext interface {
	getFromAddress() string
	getBaseURL() string
}

// PhishingTemplateContext is the context that is sent to any template, such
// as the email or landing page content.
type PhishingTemplateContext struct {
	From        string
	URL         string
	Tracker     string
	TrackingURL string
	EURL        string
	RId         string
	BaseURL     string
	BaseRecipient
}

// NewPhishingTemplateContext returns a populated PhishingTemplateContext,
// parsing the correct fields from the provided TemplateContext and recipient.
func NewPhishingTemplateContext(ctx TemplateContext, r BaseRecipient, rid string) (PhishingTemplateContext, error) {
	f, err := mail.ParseAddress(ctx.getFromAddress())
	if err != nil {
		return PhishingTemplateContext{}, err
	}
	fn := f.Name
	if fn == "" {
		fn = f.Address
	}
	templateURL, err := ExecuteTemplate(ctx.getBaseURL(), r)
	if err != nil {
		return PhishingTemplateContext{}, err
	}

	// Base URL representation without path/query
	baseURLStr := templateURL
	if u, err := url.Parse(templateURL); err == nil && u.Host != "" {
		u.Path = ""
		u.RawQuery = ""
		baseURLStr = u.String()
	}

	return PhishingTemplateContext{
		BaseRecipient: r,
		BaseURL:       baseURLStr,
		URL:           templateURL,
		TrackingURL:   templateURL,
		Tracker:       "", // Zero tracking pixels for 100% clean direct outreach
		From:          fn,
		RId:           rid,
	}, nil
}

// ValidationContext is used for validating templates and pages
type ValidationContext struct {
	FromAddress string
	BaseURL     string
}

func (vc ValidationContext) getFromAddress() string {
	return vc.FromAddress
}

func (vc ValidationContext) getBaseURL() string {
	return vc.BaseURL
}

// ValidateTemplate ensures that the provided text in the page or template
// uses the supported template variables correctly.
func ValidateTemplate(text string) error {
	vc := ValidationContext{
		FromAddress: "foo@bar.com",
		BaseURL:     "http://example.com",
	}
	td := Result{
		BaseRecipient: BaseRecipient{
			Email:     "foo@bar.com",
			FirstName: "Foo",
			LastName:  "Bar",
			Position:  "Test",
		},
		RId: "123456",
	}
	ptx, err := NewPhishingTemplateContext(vc, td.BaseRecipient, td.RId)
	if err != nil {
		return err
	}
	_, err = ExecuteTemplate(text, ptx)
	if err != nil {
		return err
	}
	return nil
}

package models

import (
	"fmt"
	"net/mail"
	"strings"
	"time"

	"github.com/gophish/gomail"
	log "github.com/gophish/gophish/logger"
	"github.com/gophish/gophish/mailer"
)

// PreviewPrefix is the standard prefix added to the rid parameter when sending
// test emails.
const PreviewPrefix = "preview-"

// EmailRequest is the structure of a request
// to send a test email to test an SMTP connection.
// This type implements the mailer.Mail interface.
type EmailRequest struct {
	Id          int64        `json:"-"`
	Template    Template     `json:"template"`
	TemplateId  int64        `json:"-"`
	Page        Page         `json:"page"`
	PageId      int64        `json:"-"`
	SMTP        SMTP         `json:"smtp"`
	URL         string       `json:"url"`
	Tracker     string       `json:"tracker" gorm:"-"`
	TrackingURL string       `json:"tracking_url" gorm:"-"`
	UserId      int64        `json:"-"`
	ErrorChan   chan (error) `json:"-" gorm:"-"`
	RId         string       `json:"id"`
	FromAddress string       `json:"-"`
	BaseRecipient
}

func (s *EmailRequest) getBaseURL() string {
	return s.URL
}

func (s *EmailRequest) getFromAddress() string {
	return s.FromAddress
}

// Validate ensures the SendTestEmailRequest structure
// is valid.
func (s *EmailRequest) Validate() error {
	switch {
	case s.Email == "":
		return ErrEmailNotSpecified
	case s.FromAddress == "" && s.SMTP.FromAddress == "":
		return ErrFromAddressNotSpecified
	}
	return nil
}

// resultDeliveryTimeout bounds how long we wait for a receiver on the result
// channel. Callers (e.g. the API handler) may have timed out and stopped
// listening; without this bound the mailer goroutine would block forever.
const resultDeliveryTimeout = 15 * time.Second

// deliver hands the terminal result to the waiting receiver, giving up after
// resultDeliveryTimeout so the sending pipeline can never wedge.
func (s *EmailRequest) deliver(err error) error {
	if s.ErrorChan == nil {
		return nil
	}
	select {
	case s.ErrorChan <- err:
	case <-time.After(resultDeliveryTimeout):
		log.Warn("timed out delivering email request result; no receiver waiting")
	}
	return nil
}

// Backoff treats temporary errors as permanent since this is expected to be a
// synchronous operation. It returns any errors given back on the ErrorChan
func (s *EmailRequest) Backoff(reason error) error {
	return s.deliver(reason)
}

// Error returns an error on the ErrorChan.
func (s *EmailRequest) Error(err error) error {
	return s.deliver(err)
}

// Success returns nil on the ErrorChan to indicate that the email was sent
// successfully.
func (s *EmailRequest) Success() error {
	return s.deliver(nil)
}

func (s *EmailRequest) GetSmtpFrom() (string, error) {
	return s.SMTP.FromAddress, nil
}

// PostEmailRequest stores a SendTestEmailRequest in the database.
func PostEmailRequest(s *EmailRequest) error {
	// Generate an ID to be used in the underlying Result object
	rid, err := generateResultId()
	if err != nil {
		return err
	}
	s.RId = fmt.Sprintf("%s%s", PreviewPrefix, rid)
	return db.Save(&s).Error
}

// GetEmailRequestByResultId retrieves the EmailRequest by the underlying rid
// parameter.
func GetEmailRequestByResultId(id string) (EmailRequest, error) {
	s := EmailRequest{}
	err := db.Table("email_requests").Where("r_id=?", id).First(&s).Error
	return s, err
}

// Generate fills in the details of a gomail.Message with the contents
// from the SendTestEmailRequest.
func (s *EmailRequest) Generate(msg *gomail.Message) error {
	f, err := mail.ParseAddress(s.Template.EnvelopeSender)
	if err != nil {
		f, err = mail.ParseAddress(s.getFromAddress())
		if err != nil {
			return err
		}
	}
	msg.SetAddressHeader("From", f.Address, f.Name)

	ptx, err := NewPhishingTemplateContext(s, s.BaseRecipient, s.RId)
	if err != nil {
		return err
	}

	url, err := ExecuteTemplate(s.URL, ptx)
	if err != nil {
		return err
	}
	s.URL = url

	// Standard RFC date
	msg.SetHeader("Date", time.Now().Format(time.RFC1123Z))

	// Add Message-Id header as described in RFC 2822 (aligned with sender domain)
	messageID, err := generateMessageID(f.Address)
	if err != nil {
		return err
	}
	msg.SetHeader("Message-Id", messageID)

	// Parse the customHeader templates. A profile header with the same key as
	// a transparency header overrides it; an empty profile value suppresses
	// the default entirely.
	hasProfileMailer := false
	for _, header := range s.SMTP.Headers {
		key, err := ExecuteTemplate(header.Key, ptx)
		if err != nil {
			log.Error(err)
		}

		value, err := ExecuteTemplate(header.Value, ptx)
		if err != nil {
			log.Error(err)
		}

		key = strings.TrimSpace(strings.TrimSuffix(strings.TrimSpace(key), ":"))
		if strings.EqualFold(key, "X-Mailer") {
			hasProfileMailer = true
		}
		if key != "" && value != "" {
			msg.SetHeader(key, value)
		}
	}

	// Transparency header: advertise the configured sending agent.
	if !hasProfileMailer {
		msg.SetHeader("X-Mailer", xMailerValue())
	}

	// Parse remaining templates
	subject, err := ExecuteTemplate(s.Template.Subject, ptx)
	if err != nil {
		log.Error(err)
	}
	subject = cleanSubjectLine(subject)
	if subject != "" {
		msg.SetHeader("Subject", subject)
	}

	msg.SetHeader("To", s.FormatAddress())

	var plainText, htmlText string
	if s.Template.Text != "" {
		plainText, err = ExecuteTemplate(s.Template.Text, ptx)
		if err != nil {
			log.Error(err)
		}
		plainText = cleanBodyText(plainText)
	}
	if s.Template.HTML != "" {
		htmlText, err = ExecuteTemplate(s.Template.HTML, ptx)
		if err != nil {
			log.Error(err)
		}
	}

	switch {
	case plainText != "" && htmlText != "":
		msg.SetBody("text/plain", plainText)
		msg.AddAlternative("text/html", htmlText)
	case htmlText != "":
		msg.SetBody("text/plain", cleanBodyText(stripHTMLTags(htmlText)))
		msg.AddAlternative("text/html", htmlText)
	case plainText != "":
		msg.SetBody("text/plain", plainText)
	}

	// Attach the files
	for _, a := range s.Template.Attachments {
		addAttachment(msg, a, ptx)
	}

	return nil
}

// GetDialer returns the mailer.Dialer for the underlying SMTP object
func (s *EmailRequest) GetDialer() (mailer.Dialer, error) {
	return s.SMTP.GetDialer()
}

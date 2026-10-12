package api

import (
	"encoding/json"
	"net/http"
	"net/mail"

	ctx "github.com/gophish/gophish/context"
	log "github.com/gophish/gophish/logger"
	"github.com/gophish/gophish/models"
	"github.com/jinzhu/gorm"
	"github.com/sirupsen/logrus"
)

// requireWorker reports whether the background worker is available, writing a
// 503 response if not. The server is started with --disable-mailer in some
// deployments; without this guard every send path panics on a nil worker.
func (as *Server) requireWorker(w http.ResponseWriter) bool {
	if as.worker == nil {
		JSONResponse(w, models.Response{
			Success: false,
			Message: "Sending is disabled: this server was started with --disable-mailer",
		}, http.StatusServiceUnavailable)
		return false
	}
	return true
}

// SendTestEmail sends a test email using the template name
// and Target given.
func (as *Server) SendTestEmail(w http.ResponseWriter, r *http.Request) {
	if !as.requireWorker(w) {
		return
	}
	s := &models.EmailRequest{
		// Buffered so the mailer can deliver its result even if we stop
		// waiting for it (e.g. after a timeout) — an unbuffered send here
		// would block the sending goroutine forever.
		ErrorChan: make(chan error, 1),
		UserId:    ctx.Get(r, "user_id").(int64),
	}
	if r.Method != "POST" {
		JSONResponse(w, models.Response{Success: false, Message: "Method not allowed"}, http.StatusBadRequest)
		return
	}
	err := json.NewDecoder(r.Body).Decode(s)
	if err != nil {
		JSONResponse(w, models.Response{Success: false, Message: "Error decoding JSON Request"}, http.StatusBadRequest)
		return
	}

	storeRequest := false

	// If a Template is not specified use a default
	if s.Template.Name == "" {
		text := "Hello,\n\nThis is a test email verifying that your email sending configuration is active and working properly.\n\n" +
			"Sender: {{.From}}\n" +
			"Recipient: {{.Email}}\n\n" +
			"Best regards,\nTanim"
		t := models.Template{
			Subject: "SMTP Configuration Test",
			Text:    text,
		}
		s.Template = t
	} else {
		// Get the Template requested by name
		s.Template, err = models.GetTemplateByName(s.Template.Name, s.UserId)
		if err == gorm.ErrRecordNotFound {
			log.WithFields(logrus.Fields{
				"template": s.Template.Name,
			}).Error("Template does not exist")
			JSONResponse(w, models.Response{Success: false, Message: models.ErrTemplateNotFound.Error()}, http.StatusBadRequest)
			return
		} else if err != nil {
			log.Error(err)
			JSONResponse(w, models.Response{Success: false, Message: err.Error()}, http.StatusBadRequest)
			return
		}
		s.TemplateId = s.Template.Id
		// We'll only save the test request to the database if there is a
		// user-specified template to use.
		storeRequest = true
	}

	if s.Page.Name != "" {
		s.Page, err = models.GetPageByName(s.Page.Name, s.UserId)
		if err == gorm.ErrRecordNotFound {
			log.WithFields(logrus.Fields{
				"page": s.Page.Name,
			}).Error("Page does not exist")
			JSONResponse(w, models.Response{Success: false, Message: models.ErrPageNotFound.Error()}, http.StatusBadRequest)
			return
		} else if err != nil {
			log.Error(err)
			JSONResponse(w, models.Response{Success: false, Message: err.Error()}, http.StatusBadRequest)
			return
		}
		s.PageId = s.Page.Id
	}

	// If a complete sending profile is provided use it
	if err := s.SMTP.Validate(); err != nil {
		// Otherwise get the SMTP requested by name
		smtp, lookupErr := models.GetSMTPByName(s.SMTP.Name, s.UserId)
		// If the Sending Profile doesn't exist, let's err on the side
		// of caution and assume that the validation failure was more important.
		if lookupErr != nil {
			log.Error(err)
			JSONResponse(w, models.Response{Success: false, Message: err.Error()}, http.StatusBadRequest)
			return
		}
		s.SMTP = smtp
	}

	_, err = mail.ParseAddress(s.Template.EnvelopeSender)
	if err != nil {
		_, err = mail.ParseAddress(s.SMTP.FromAddress)
		if err != nil {
			JSONResponse(w, models.Response{Success: false, Message: err.Error()}, http.StatusInternalServerError)
			return
		} else {
			s.FromAddress = s.SMTP.FromAddress
		}
	} else {
		s.FromAddress = s.Template.EnvelopeSender
	}

	// Validate the given request
	if err = s.Validate(); err != nil {
		JSONResponse(w, models.Response{Success: false, Message: err.Error()}, http.StatusBadRequest)
		return
	}

	// Store the request if this wasn't the default template
	if storeRequest {
		err = models.PostEmailRequest(s)
		if err != nil {
			log.Error(err)
			JSONResponse(w, models.Response{Success: false, Message: err.Error()}, http.StatusInternalServerError)
			return
		}
	}
	// Send the test email
	err = as.worker.SendTestEmail(s)
	if err != nil {
		log.Error(err)
		JSONResponse(w, models.Response{Success: false, Message: err.Error()}, http.StatusInternalServerError)
		return
	}
	JSONResponse(w, models.Response{Success: true, Message: "Email Sent"}, http.StatusOK)
}

// CustomEmailRequest defines the payload for direct 1-to-1 outreach emails
type CustomEmailRequest struct {
	To          string `json:"to"`
	Email       string `json:"email"`
	FirstName   string `json:"first_name"`
	LastName    string `json:"last_name"`
	Company     string `json:"company"`
	Position    string `json:"position"`
	CustomField string `json:"custom_field"`
	Subject     string `json:"subject"`
	Text        string `json:"text"`
	HTML        string `json:"html"`
	SMTP        string `json:"smtp"`
	URL         string `json:"url"`
}

// SendCustomEmail handles direct 1-to-1 personalized outreach email dispatch
func (as *Server) SendCustomEmail(w http.ResponseWriter, r *http.Request) {
	if !as.requireWorker(w) {
		return
	}
	if r.Method != "POST" {
		JSONResponse(w, models.Response{Success: false, Message: "Method not allowed"}, http.StatusMethodNotAllowed)
		return
	}

	userId := ctx.Get(r, "user_id").(int64)
	req := CustomEmailRequest{}
	err := json.NewDecoder(r.Body).Decode(&req)
	if err != nil {
		JSONResponse(w, models.Response{Success: false, Message: "Error decoding JSON payload: " + err.Error()}, http.StatusBadRequest)
		return
	}

	destEmail := req.To
	if destEmail == "" {
		destEmail = req.Email
	}
	if destEmail == "" {
		JSONResponse(w, models.Response{Success: false, Message: "Missing recipient email address ('to' or 'email')"}, http.StatusBadRequest)
		return
	}

	if req.Subject == "" {
		JSONResponse(w, models.Response{Success: false, Message: "Missing subject line"}, http.StatusBadRequest)
		return
	}

	// Lookup SMTP profile
	var smtp models.SMTP
	if req.SMTP != "" {
		smtp, err = models.GetSMTPByName(req.SMTP, userId)
		if err != nil {
			JSONResponse(w, models.Response{Success: false, Message: "SMTP profile not found: " + req.SMTP}, http.StatusBadRequest)
			return
		}
	} else {
		// Fallback to first available SMTP profile
		smtps, err := models.GetSMTPs(userId)
		if err != nil || len(smtps) == 0 {
			JSONResponse(w, models.Response{Success: false, Message: "No active SMTP profile configured"}, http.StatusBadRequest)
			return
		}
		smtp = smtps[0]
	}

	emailReq := &models.EmailRequest{
		ErrorChan: make(chan error, 1),
		UserId:    userId,
		Template: models.Template{
			Name:    "Custom_Direct_Send",
			Subject: req.Subject,
			Text:    req.Text,
			HTML:    req.HTML,
		},
		SMTP:        smtp,
		FromAddress: smtp.FromAddress,
		URL:         req.URL,
		BaseRecipient: models.BaseRecipient{
			Email:       destEmail,
			FirstName:   req.FirstName,
			LastName:    req.LastName,
			Company:     req.Company,
			Position:    req.Position,
			CustomField: req.CustomField,
		},
	}

	err = as.worker.SendTestEmail(emailReq)
	if err != nil {
		log.Error(err)
		JSONResponse(w, models.Response{Success: false, Message: "Failed to dispatch email: " + err.Error()}, http.StatusInternalServerError)
		return
	}

	JSONResponse(w, models.Response{
		Success: true,
		Message: "Personalized email dispatched successfully to " + destEmail,
	}, http.StatusOK)
}

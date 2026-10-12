package llm

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Model represents the hardcoded LLM model configuration
const Model = "openrouter/cognitivecomputations/dolphin-mistral-24b-venice-edition"

// OpenRouterAPIURL is the base URL for OpenRouter API
const OpenRouterAPIURL = "https://openrouter.ai/api/v1/chat/completions"

// APIKey is the OpenRouter API key - this would typically come from config
var APIKey = ""

// Message represents a chat message
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// Request represents the OpenRouter API request
type Request struct {
	Model       string    `json:"model"`
	Messages    []Message `json:"messages"`
	Temperature float64   `json:"temperature,omitempty"`
	MaxTokens   int       `json:"max_tokens,omitempty"`
	Stream      bool      `json:"stream,omitempty"`
}

// Response represents the OpenRouter API response
type Response struct {
	ID      string `json:"id"`
	Object  string `json:"object"`
	Created int64  `json:"created"`
	Model   string `json:"model"`
	Choices []struct {
		Index        int     `json:"index"`
		Message      Message `json:"message"`
		FinishReason string  `json:"finish_reason"`
	} `json:"choices"`
	Usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	} `json:"usage"`
}

// Client represents the LLM client
type Client struct {
	apiKey     string
	model      string
	httpClient *http.Client
}

// NewClient creates a new LLM client with the hardcoded model
func NewClient(apiKey string) *Client {
	return &Client{
		apiKey: apiKey,
		model:  Model, // Hardcoded model as requested
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// GenerateText generates text using the LLM with no censorship
func (c *Client) GenerateText(prompt string, systemMessage ...string) (string, error) {
	messages := []Message{}

	// Add system message if provided (for context/behavior control)
	if len(systemMessage) > 0 {
		messages = append(messages, Message{
			Role:    "system",
			Content: systemMessage[0],
		})
	}

	// Add user prompt
	messages = append(messages, Message{
		Role:    "user",
		Content: prompt,
	})

	request := Request{
		Model:       c.model, // Using hardcoded model
		Messages:    messages,
		Temperature: 0.7,   // Default temperature for creativity
		MaxTokens:   4096,  // Large token limit for long responses
		Stream:      false, // Non-streaming for simplicity
	}

	// Marshal request to JSON
	requestBody, err := json.Marshal(request)
	if err != nil {
		return "", fmt.Errorf("failed to marshal request: %v", err)
	}

	// Create HTTP request
	req, err := http.NewRequest("POST", OpenRouterAPIURL, bytes.NewBuffer(requestBody))
	if err != nil {
		return "", fmt.Errorf("failed to create request: %v", err)
	}

	// Set headers
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.apiKey))

	// Make the request
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("HTTP request failed: %v", err)
	}
	defer resp.Body.Close()

	// Check status code
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("API request failed with status %d: %s", resp.StatusCode, string(body))
	}

	// Parse response
	var response Response
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return "", fmt.Errorf("failed to parse response: %v", err)
	}

	// Check if we got a valid response
	if len(response.Choices) == 0 {
		return "", fmt.Errorf("no choices returned from API")
	}

	// Return the generated text (uncensored, raw response)
	return response.Choices[0].Message.Content, nil
}

// GenerateEmailSubject generates an email subject using LLM
func (c *Client) GenerateEmailSubject(context string) (string, error) {
	prompt := fmt.Sprintf(`Generate a compelling email subject line for the following context:
%s

Return ONLY the subject line, nothing else.`, context)

	return c.GenerateText(prompt, "You are an expert email marketer. Generate engaging, high-open-rate subject lines.")
}

// GenerateEmailBody generates an email body using LLM
func (c *Client) GenerateEmailBody(subject, context string) (string, error) {
	prompt := fmt.Sprintf(`Write a compelling email body for the following subject and context:

Subject: %s
Context: %s

Write a professional, engaging email body that will drive opens and clicks. Include a clear call-to-action.`, subject, context)

	return c.GenerateText(prompt, "You are an expert email copywriter. Write engaging, conversion-focused email content.")
}

// AnalyzeEmailContent analyzes email content for deliverability and quality
func (c *Client) AnalyzeEmailContent(emailContent string) (string, error) {
	prompt := fmt.Sprintf(`Analyze the following email content for deliverability issues, spam triggers, and quality:

%s

Provide a detailed analysis including:
1. Spam score assessment (1-10 scale)
2. Potential spam trigger words/phrases
3. Deliverability recommendations
4. Content quality score (1-10 scale)
5. Suggestions for improvement`, emailContent)

	return c.GenerateText(prompt, "You are an email deliverability expert. Analyze content for spam filters, blacklists, and best practices.")
}

// SetAPIKey sets the API key for the LLM client
func SetAPIKey(key string) {
	APIKey = key
}

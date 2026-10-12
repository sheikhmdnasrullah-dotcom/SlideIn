package models

import (
	"archive/zip"
	"bufio"
	"bytes"
	"encoding/base64"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/check.v1"
)

func (s *ModelsSuite) TestAttachment(c *check.C) {
	ptx := PhishingTemplateContext{
		BaseRecipient: BaseRecipient{
			FirstName: "Foo",
			LastName:  "Bar",
			Email:     "foo@bar.com",
			Position:  "Space Janitor",
		},
		BaseURL:     "http://testurl.com",
		URL:         "http://testurl.com/?rid=1234567",
		TrackingURL: "http://testurl.local/track?rid=1234567",
		Tracker:     "<img alt='' style='display: none' src='http://testurl.local/track?rid=1234567'/>",
		From:        "From Address",
		RId:         "1234567",
	}

	files, err := ioutil.ReadDir("testdata")
	if err != nil {
		log.Fatalf("Failed to open attachment folder 'testdata': %v\n", err)
	}
	for _, ff := range files {
		if !ff.IsDir() && !strings.Contains(ff.Name(), "templated") {
			fname := ff.Name()
			fmt.Printf("Checking attachment file -> %s\n", fname)
			data := readFile("testdata/" + fname)
			if filepath.Ext(fname) == ".b64" {
				fname = fname[:len(fname)-4]
			}
			a := Attachment{
				Content: data,
				Name:    fname,
			}
			t, err := a.ApplyTemplate(ptx)
			c.Assert(err, check.Equals, nil)
			c.Assert(a.vanillaFile, check.Equals, strings.Contains(fname, "without-vars"))
			c.Assert(a.vanillaFile, check.Not(check.Equals), strings.Contains(fname, "with-vars"))

			// Verfify template was applied as expected
			tt, err := ioutil.ReadAll(t)
			if err != nil {
				log.Fatalf("Failed to parse templated file '%s': %v\n", fname, err)
			}
			expectedOutput := readFile("testdata/" + strings.TrimSuffix(ff.Name(), filepath.Ext(ff.Name())) + ".templated" + filepath.Ext(ff.Name())) // e.g text-file-with-vars.templated.txt
			if isZipAttachment(fname) {
				assertZipContentsEqual(c, tt, expectedOutput, fname)
			} else {
				templatedFile := base64.StdEncoding.EncodeToString(tt)
				c.Assert(templatedFile, check.Equals, expectedOutput)
			}
		}
	}
}

func isZipAttachment(name string) bool {
	switch strings.ToLower(filepath.Ext(name)) {
	case ".docx", ".docm", ".pptx", ".xlsx", ".xlsm":
		return true
	}
	return false
}

// assertZipContentsEqual compares two zip archives by entry names and
// uncompressed contents instead of raw bytes: deflate output varies across
// Go toolchains, but the templated content must be identical.
func assertZipContentsEqual(c *check.C, obtained []byte, expectedB64, fname string) {
	expectedRaw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(expectedB64))
	c.Assert(err, check.Equals, nil, check.Commentf("decoding fixture for %s", fname))
	c.Assert(unzipToMap(c, obtained, fname), check.DeepEquals, unzipToMap(c, expectedRaw, fname),
		check.Commentf("zip contents differ for %s", fname))
}

func unzipToMap(c *check.C, raw []byte, fname string) map[string]string {
	zr, err := zip.NewReader(bytes.NewReader(raw), int64(len(raw)))
	c.Assert(err, check.Equals, nil, check.Commentf("unzipping %s", fname))
	out := map[string]string{}
	for _, f := range zr.File {
		rc, err := f.Open()
		c.Assert(err, check.Equals, nil, check.Commentf("opening entry in %s", fname))
		content, err := ioutil.ReadAll(rc)
		rc.Close()
		c.Assert(err, check.Equals, nil, check.Commentf("reading entry in %s", fname))
		out[f.Name] = string(content)
	}
	return out
}

func readFile(fname string) string {
	f, err := os.Open(fname)
	if err != nil {
		log.Fatalf("Failed to open file '%s': %v\n", fname, err)
	}
	reader := bufio.NewReader(f)
	content, err := ioutil.ReadAll(reader)
	if err != nil {
		log.Fatalf("Failed to read file '%s': %v\n", fname, err)
	}
	data := ""
	if filepath.Ext(fname) == ".b64" {
		data = string(content)
	} else {
		data = base64.StdEncoding.EncodeToString(content)
	}
	return data
}

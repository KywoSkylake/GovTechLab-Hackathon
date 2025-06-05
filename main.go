package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

type Activity struct {
	Date        string `json:"date"`
	Description string `json:"type"`
	Speaker     string `json:"description"`
	Link        string `json:"link,omitempty"`
}

func scrapeDossier(dossierID string) ([]Activity, error) {
	url := fmt.Sprintf("https://www.chd.lu/en/dossier/%s", dossierID)

	res, err := http.Get(url)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()

	if res.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("status code %d", res.StatusCode)
	}

	doc, err := goquery.NewDocumentFromReader(res.Body)
	if err != nil {
		return nil, err
	}

	var activities []Activity
	doc.Find(".table tbody tr").Each(func(i int, s *goquery.Selection) {
		tds := s.Find("td")
		if tds.Length() < 3 {
			return
		}

		date := strings.TrimSpace(tds.Eq(0).Text())
		description := strings.TrimSpace(tds.Eq(1).Text())
		speaker := strings.TrimSpace(tds.Eq(2).Text())

		var link string
		if tds.Length() > 3 {
			l, exists := tds.Eq(3).Find("a").Attr("href")
			if exists {
				if strings.HasPrefix(l, "/") {
					l = "https://www.chd.lu" + l
				}
				link = l
			}
		}

		activities = append(activities, Activity{
			Date:        date,
			Description: description,
			Speaker:     speaker,
			Link:        link,
		})
	})

	return activities, nil
}

func saveActivities(dossierID string, activities []Activity) error {
	dir := "scrape"
	if err := os.MkdirAll(dir, os.ModePerm); err != nil {
		return err
	}

	filePath := filepath.Join(dir, fmt.Sprintf("%s.json", dossierID))
	file, err := os.Create(filePath)
	if err != nil {
		return err
	}
	defer file.Close()

	return json.NewEncoder(file).Encode(struct {
		DossierID  string     `json:"dossier_id"`
		Activities []Activity `json:"activities"`
	}{
		DossierID:  dossierID,
		Activities: activities,
	})
}
func loadDossierStrings(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("cannot open file: %w", err)
	}
	defer file.Close()

	var dossiers []string
	err = json.NewDecoder(file).Decode(&dossiers)
	if err != nil {
		return nil, fmt.Errorf("cannot decode JSON: %w", err)
	}

	return dossiers, nil
}
func main() {
	dossiers, err := loadDossierStrings("dossiers.json")
	if err != nil {
		log.Fatalf("Failed to load dossier list: %v", err)
	}

	for _, id := range dossiers {
		fmt.Printf("Scraping dossier %s...\n", id)
		activities, err := scrapeDossier(id)
		if err != nil {
			log.Printf("Error on dossier %s: %v\n", id, err)
			continue
		}
		if len(activities) == 0 {
			continue
		}
		err = saveActivities(id, activities)
		if err != nil {
			log.Printf("Failed to save dossier %d: %v\n", id, err)
		}
		// time.Sleep(500 * time.Millisecond) // Rate limiting
	}
}

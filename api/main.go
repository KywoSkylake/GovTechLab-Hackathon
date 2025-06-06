package main

import (
	"encoding/json"
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
)

// Entry represents a single record in your JSON file.
type Entry struct {
	Date           string `json:"date"`
	Type           string `json:"type"`
	Description    string `json:"description"`
	Link           string `json:"link,omitempty"`
	DossierID      string `json:"dossier_id"`
	Category       string `json:"category"`
	CategoryPretty string `json:"category_pretty"`
}

var entries []Entry

func main() {
	// Load JSON file
	err := loadJSONFile(getEnv("ACTIVITY_FILE", "../data_process/activities.json"))
	if err != nil {
		panic("Failed to load JSON data: " + err.Error())
	}

	router := gin.Default()
	router.GET("/entries", getAllEntries)
	router.GET("/entries/category/:category", getEntriesByCategory)
	router.GET("/categories", getAllCategories)

	router.Run("0.0.0.0:8080")
}

func getEnv(key, fallback string) string {
	value, exists := os.LookupEnv(key)
	if !exists {
		value = fallback
	}
	return value
}

func loadJSONFile(filename string) error {
	data, err := os.ReadFile(filename)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, &entries)
}

func getAllEntries(c *gin.Context) {
	c.IndentedJSON(http.StatusOK, entries)
}

func getEntriesByCategory(c *gin.Context) {
	entryCategorie := c.Param("category")
	var results []Entry

	for _, e := range entries {
		if e.Category == entryCategorie {
			results = append(results, e)
		}
	}

	if len(results) == 0 {
		c.IndentedJSON(http.StatusNotFound, gin.H{"message": "no entries found for that category"})
		return
	}

	c.IndentedJSON(http.StatusOK, results)
}

func getAllCategories(c *gin.Context) {
	categoryMap := make(map[string]bool)
	categoryCount := getCategoryCounts()
	categories := []gin.H{}

	for _, e := range entries {
		if !categoryMap[e.Category] {
			categoryMap[e.Category] = true
			categories = append(categories, gin.H{
				"category":          e.CategoryPretty,
				"link":              "http://localhost:8080/entries/category/" + e.Category,
				"number of entries": categoryCount[e.Category],
			})
		}
	}

	c.IndentedJSON(http.StatusOK, categories)
}

func getCategoryCounts() map[string]int {
	counts := make(map[string]int)
	for _, e := range entries {
		counts[e.Category]++
	}
	return counts
}

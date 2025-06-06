package main

import (
	"encoding/json"
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
)

// Activity represents a single record in your JSON file.
type Activity struct {
	Date           string `json:"date"`
	Type           string `json:"type"`
	Description    string `json:"description"`
	Link           string `json:"link,omitempty"`
	DossierID      string `json:"dossier_id"`
	Category       string `json:"category"`
	CategoryPretty string `json:"category_pretty"`
}

var activities []Activity

func main() {
	// Load JSON file
	err := loadJSONFile(getEnv("ACTIVITY_FILE", "../data_process/activities.json"))
	if err != nil {
		panic("Failed to load JSON data: " + err.Error())
	}

	router := gin.Default()
	router.GET("/activities", getAllActivities)
	router.GET("/activities/category/:category", getActivitiesByCategory)
	router.GET("/activities/dossier/:dossier", getActivitiesByDossier)
	router.GET("/categories", getAllCategories)
	router.GET("/dossiers", getAllDossiers)

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

	err = json.Unmarshal(data, &activities)
	if err != nil {
		return err
	}

	return nil
}

func getAllActivities(c *gin.Context) {
	c.IndentedJSON(http.StatusOK, activities)
}

func getActivitiesByCategory(c *gin.Context) {
	activityCategorie := c.Param("category")
	var results []Activity

	for _, e := range activities {
		if e.Category == activityCategorie {
			results = append(results, e)
		}
	}

	if len(results) == 0 {
		c.IndentedJSON(http.StatusNotFound, gin.H{"message": "no activities found for that category"})
		return
	}

	c.IndentedJSON(http.StatusOK, results)
}

func getAllCategories(c *gin.Context) {
	categoryMap := make(map[string]bool)
	categoryCount := getCategoryCounts()
	categories := []gin.H{}

	for _, e := range activities {
		if !categoryMap[e.Category] {
			categoryMap[e.Category] = true
			categories = append(categories, gin.H{
				"category":             e.CategoryPretty,
				"link":                 "http://localhost:8080/activities/category/" + e.Category,
				"number of activities": categoryCount[e.Category],
			})
		}
	}

	c.IndentedJSON(http.StatusOK, categories)
}

func getCategoryCounts() map[string]int {
	counts := make(map[string]int)
	for _, e := range activities {
		counts[e.Category]++
	}
	return counts
}

func getActivitiesByDossier(c *gin.Context) {
	activityDossier := c.Param("dossier")
	var results []Activity

	for _, e := range activities {
		if e.DossierID == activityDossier {
			results = append(results, e)
		}
	}

	if len(results) == 0 {
		c.IndentedJSON(http.StatusNotFound, gin.H{"message": "no activities found for that category"})
		return
	}

	c.IndentedJSON(http.StatusOK, results)
}

func getAllDossiers(c *gin.Context) {
	dossierMap := make(map[string]bool)
	dossierCount := getDossierCounts()
	dossiers := []gin.H{}

	for _, e := range activities {
		if !dossierMap[e.DossierID] {
			dossierMap[e.DossierID] = true
			dossiers = append(dossiers, gin.H{
				"dossier":              e.DossierID,
				"link":                 "http://localhost:8080/activities/dossier/" + e.DossierID,
				"number of activities": dossierCount[e.DossierID],
			})
		}
	}

	c.IndentedJSON(http.StatusOK, dossiers)
}

func getDossierCounts() map[string]int {
	counts := make(map[string]int)
	for _, e := range activities {
		counts[e.DossierID]++
	}
	return counts
}

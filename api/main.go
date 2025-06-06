package main

import (
	"encoding/json"
	"net/http"
	"net/url"
	"os"

	_ "chd_api/docs" // Replace with your actual module name

	"github.com/gin-gonic/gin"
	swaggerFiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"
)

// ActivityFull represents a single record in your JSON file.
type ActivityFull struct {
	Activity
	Dossier
}

func (r ActivityFull) small() Activity {
	return r.Activity
}

func (r ActivityFull) dossier() Dossier {
	return r.Dossier
}

// Activity represents a single record in your JSON file.
type Activity struct {
	Date           string `json:"date"`
	Type           string `json:"type"`
	Description    string `json:"description"`
	Link           string `json:"link,omitempty"`
	Category       string `json:"category"`
	CategoryPretty string `json:"category_pretty"`
}

type Dossier struct {
	DossierID      string `json:"dossier_id"`
	DossierName    string `json:"dossier_name"`
	DossierSatus   string `json:"dossier_status"`
	DossierAuthors string `json:"dossier_authors"`
	DossierContent string `json:"dossier_content"`
}

type DossierActivities struct {
	Dossier
	Activites []Activity `json:"activities"`
}

var activities []ActivityFull

// @title           CHD Activities API
// @version         1.0
// @description     Provides access to CHD activity data by category and dossier.
// @host            localhost:8080
// @BasePath        /
func main() {
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
	router.GET("/swagger/*any", ginSwagger.WrapHandler(swaggerFiles.Handler))

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

	for i := range activities {
		if activities[i].Link != "" {
			parsedURL, err := url.Parse(activities[i].Link)
			if err == nil {
				parsedURL.Path = url.PathEscape(parsedURL.Path)
				activities[i].Link = parsedURL.String()
			}
		}
	}

	return nil
}

// @Summary      Get all activities
// @Description  Returns a list of all activities
// @Tags         activities
// @Produce      json
// @Success      200  {array}  Activity
// @Router       /activities [get]
func getAllActivities(c *gin.Context) {
	c.IndentedJSON(http.StatusOK, activities)
}

// @Summary      Get activities by category
// @Description  Returns activities for a given category
// @Tags         activities
// @Produce      json
// @Param        category  path      string  true  "Category"
// @Success      200  {array}  Activity
// @Failure      404  {object}  map[string]string
// @Router       /activities/category/{category} [get]
func getActivitiesByCategory(c *gin.Context) {
	activityCategorie := c.Param("category")
	var results []ActivityFull

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

// @Summary      List categories
// @Description  Get all unique categories with activity count
// @Tags         categories
// @Produce      json
// @Success      200  {array}  map[string]interface{}
// @Router       /categories [get]
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

// @Summary      Get activities by dossier
// @Description  Returns activities for a given dossier
// @Tags         activities
// @Produce      json
// @Param        dossier  path      string  true  "Dossier"
// @Success      200  {array}  DossierActivities
// @Failure      404  {object}  map[string]string
// @Router       /activities/dossier/{dossier} [get]
func getActivitiesByDossier(c *gin.Context) {
	activityDossier := c.Param("dossier")
	var results []Activity
	var dossier Dossier

	for _, e := range activities {
		if e.DossierID == activityDossier {
			results = append(results, e.small())
			dossier = e.Dossier
		}
	}

	if len(results) == 0 {

		c.IndentedJSON(http.StatusNotFound, gin.H{"message": "no activities found for that category"})
		return
	}

	c.IndentedJSON(http.StatusOK, DossierActivities{Dossier: dossier, Activites: results})
}

// @Summary      List dossiers
// @Description  Get all unique dossiers with activity count
// @Tags         dossiers
// @Produce      json
// @Success      200  {array}  map[string]interface{}
// @Router       /dossiers [get]
func getAllDossiers(c *gin.Context) {
	dossierMap := make(map[string]bool)
	dossierCount := getDossierCounts()
	dossiers := []gin.H{}

	for _, e := range activities {
		if !dossierMap[e.DossierID] {
			dossierMap[e.DossierID] = true
			dossiers = append(dossiers, gin.H{
				"dossier id":           e.DossierID,
				"dossier name":         e.DossierName,
				"dossier status":       e.DossierSatus,
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

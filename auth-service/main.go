package main

import (
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"
)

// User represents a user in the system
type User struct {
	ID        string    `json:"id"`
	Email     string    `json:"email"`
	Password  string    `json:"-"` // Never expose password in JSON
	Name      string    `json:"name"`
	Avatar    string    `json:"avatar,omitempty"`
	Role      string    `json:"role"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// UserProfile is the public profile (no sensitive data)
type UserProfile struct {
	ID        string    `json:"id"`
	Email     string    `json:"email"`
	Name      string    `json:"name"`
	Avatar    string    `json:"avatar,omitempty"`
	Role      string    `json:"role"`
	CreatedAt time.Time `json:"created_at"`
}

// LoginRequest for user login
type LoginRequest struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required,min=6"`
}

// RegisterRequest for user registration
type RegisterRequest struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required,min=6"`
	Name     string `json:"name" binding:"required,min=2"`
}

// UpdateProfileRequest for updating user profile
type UpdateProfileRequest struct {
	Name   string `json:"name,omitempty"`
	Avatar string `json:"avatar,omitempty"`
}

// AuthResponse returned after successful login/register
type AuthResponse struct {
	Token   string      `json:"token"`
	User    UserProfile `json:"user"`
	Message string      `json:"message"`
}

// In-memory user store (replace with database in production)
var (
	users     = make(map[string]*User) // email -> user
	usersByID = make(map[string]*User) // id -> user
	userMutex sync.RWMutex
	jwtSecret = []byte("your-secret-key-change-in-production")
)

func init() {
	// Create a default admin user
	hashedPassword, _ := bcrypt.GenerateFromPassword([]byte("admin123"), bcrypt.DefaultCost)
	adminUser := &User{
		ID:        uuid.New().String(),
		Email:     "admin@us.inc",
		Password:  string(hashedPassword),
		Name:      "Admin User",
		Role:      "admin",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}
	users[adminUser.Email] = adminUser
	usersByID[adminUser.ID] = adminUser

	// Create test user
	testPassword, _ := bcrypt.GenerateFromPassword([]byte("testuser#123"), bcrypt.DefaultCost)
	testUser := &User{
		ID:        uuid.New().String(),
		Email:     "testuser1@us.inc",
		Password:  string(testPassword),
		Name:      "Test User",
		Role:      "user",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}
	users[testUser.Email] = testUser
	usersByID[testUser.ID] = testUser
}

func main() {
	// Set Gin mode
	if os.Getenv("GIN_MODE") == "" {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.Default()

	// CORS middleware
	r.Use(func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})

	// Health check
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy", "service": "auth-service"})
	})

	// Auth routes
	auth := r.Group("/auth")
	{
		auth.POST("/register", register)
		auth.POST("/login", login)
		auth.POST("/logout", logout)
		auth.GET("/verify", authMiddleware(), verifyToken)
	}

	// User routes (protected)
	userRoutes := r.Group("/users")
	userRoutes.Use(authMiddleware())
	{
		userRoutes.GET("/me", getProfile)
		userRoutes.PUT("/me", updateProfile)
		userRoutes.GET("/:id", getUserByID)
		userRoutes.GET("/", listUsers) // Admin only
	}

	port := os.Getenv("AUTH_PORT")
	if port == "" {
		port = "8001"
	}

	log.Printf("🔐 Auth Service starting on port %s", port)
	log.Printf("   Default admin: admin@us.inc / admin123")
	log.Printf("   Test user: testuser1@us.inc / testuser#123")

	if err := r.Run(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}

// register creates a new user account
func register(c *gin.Context) {
	var req RegisterRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request: " + err.Error()})
		return
	}

	userMutex.Lock()
	defer userMutex.Unlock()

	// Check if user already exists
	if _, exists := users[req.Email]; exists {
		c.JSON(http.StatusConflict, gin.H{"error": "Email already registered"})
		return
	}

	// Hash password
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to process password"})
		return
	}

	// Create user
	user := &User{
		ID:        uuid.New().String(),
		Email:     req.Email,
		Password:  string(hashedPassword),
		Name:      req.Name,
		Role:      "user",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	users[user.Email] = user
	usersByID[user.ID] = user

	// Generate JWT token
	token, err := generateToken(user)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	c.JSON(http.StatusCreated, AuthResponse{
		Token:   token,
		User:    toProfile(user),
		Message: "Registration successful",
	})
}

// login authenticates a user
func login(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request: " + err.Error()})
		return
	}

	userMutex.RLock()
	user, exists := users[req.Email]
	userMutex.RUnlock()

	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}

	// Check password
	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(req.Password)); err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}

	// Generate JWT token
	token, err := generateToken(user)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	c.JSON(http.StatusOK, AuthResponse{
		Token:   token,
		User:    toProfile(user),
		Message: "Login successful",
	})
}

// logout invalidates the token (client-side handling)
func logout(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"message": "Logout successful"})
}

// verifyToken checks if the current token is valid
func verifyToken(c *gin.Context) {
	user, _ := c.Get("user")
	c.JSON(http.StatusOK, gin.H{
		"valid": true,
		"user":  toProfile(user.(*User)),
	})
}

// getProfile returns the current user's profile
func getProfile(c *gin.Context) {
	user, _ := c.Get("user")
	c.JSON(http.StatusOK, toProfile(user.(*User)))
}

// updateProfile updates the current user's profile
func updateProfile(c *gin.Context) {
	var req UpdateProfileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}

	user, _ := c.Get("user")
	currentUser := user.(*User)

	userMutex.Lock()
	defer userMutex.Unlock()

	if req.Name != "" {
		currentUser.Name = req.Name
	}
	if req.Avatar != "" {
		currentUser.Avatar = req.Avatar
	}
	currentUser.UpdatedAt = time.Now()

	c.JSON(http.StatusOK, gin.H{
		"message": "Profile updated",
		"user":    toProfile(currentUser),
	})
}

// getUserByID returns a user by their ID
func getUserByID(c *gin.Context) {
	id := c.Param("id")

	userMutex.RLock()
	user, exists := usersByID[id]
	userMutex.RUnlock()

	if !exists {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	c.JSON(http.StatusOK, toProfile(user))
}

// listUsers returns all users (admin only)
func listUsers(c *gin.Context) {
	currentUser, _ := c.Get("user")
	if currentUser.(*User).Role != "admin" {
		c.JSON(http.StatusForbidden, gin.H{"error": "Admin access required"})
		return
	}

	userMutex.RLock()
	defer userMutex.RUnlock()

	profiles := make([]UserProfile, 0, len(users))
	for _, user := range users {
		profiles = append(profiles, toProfile(user))
	}

	c.JSON(http.StatusOK, gin.H{
		"users": profiles,
		"total": len(profiles),
	})
}

// generateToken creates a JWT token for a user
func generateToken(user *User) (string, error) {
	claims := jwt.MapClaims{
		"user_id": user.ID,
		"email":   user.Email,
		"role":    user.Role,
		"exp":     time.Now().Add(24 * time.Hour).Unix(),
		"iat":     time.Now().Unix(),
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(jwtSecret)
}

// authMiddleware validates JWT tokens
func authMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Authorization header required"})
			c.Abort()
			return
		}

		// Extract token from "Bearer <token>"
		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || parts[0] != "Bearer" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid authorization format"})
			c.Abort()
			return
		}

		tokenString := parts[1]

		// Parse and validate token
		token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, jwt.ErrSignatureInvalid
			}
			return jwtSecret, nil
		})

		if err != nil || !token.Valid {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid or expired token"})
			c.Abort()
			return
		}

		// Extract claims
		claims, ok := token.Claims.(jwt.MapClaims)
		if !ok {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid token claims"})
			c.Abort()
			return
		}

		// Get user from store
		userID := claims["user_id"].(string)
		userMutex.RLock()
		user, exists := usersByID[userID]
		userMutex.RUnlock()

		if !exists {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "User not found"})
			c.Abort()
			return
		}

		// Set user in context
		c.Set("user", user)
		c.Next()
	}
}

// toProfile converts User to UserProfile (removes sensitive data)
func toProfile(user *User) UserProfile {
	return UserProfile{
		ID:        user.ID,
		Email:     user.Email,
		Name:      user.Name,
		Avatar:    user.Avatar,
		Role:      user.Role,
		CreatedAt: user.CreatedAt,
	}
}

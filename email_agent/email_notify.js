/*******************************************************
 * email_notifier.js
 * Independent email notification component
 * Sends completion emails via Gmail after app runs
 *******************************************************/
import nodemailer from 'nodemailer';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import dotenv from 'dotenv';
import OpenAI from 'openai';

dotenv.config();

// Get the directory name using ES modules
const __dirname = dirname(fileURLToPath(import.meta.url));

// File path for email recipients
const EMAIL_RECIPIENTS_FILE = path.join(__dirname, 'email_recipients.txt');

// Initialize OpenAI client for generating personalized openings
const openai = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY,
    maxRetries: 2,
    timeout: 30000
});

/**
 * Load email recipients from file
 * @returns {Array<string>} Array of email addresses
 */
async function loadEmailRecipients() {
    try {
        const content = await fs.readFile(EMAIL_RECIPIENTS_FILE, 'utf-8');
        const emails = content
            .split('\n')
            .map(email => email.trim())
            .filter(email => email && email.includes('@'));
        
        console.log(`📧 Loaded ${emails.length} email recipients`);
        return emails;
    } catch (error) {
        console.log(`⚠️ Could not load email recipients: ${error.message}`);
        return [];
    }
}

/**
 * Create Gmail transporter
 * @returns {Object|null} Nodemailer transporter or null if failed
 */
function createGmailTransporter() {
    try {
        const user = process.env.GMAIL_USER;
        const pass = process.env.GMAIL_APP_PASSWORD;
        
        if (!user || !pass) {
            console.log('⚠️ Gmail credentials not configured in .env file');
            console.log(`GMAIL_USER: ${user ? 'Set' : 'Not set'}`);
            console.log(`GMAIL_APP_PASSWORD: ${pass ? 'Set' : 'Not set'}`);
            return null;
        }
        
        // Remove any spaces from the app password (Gmail displays them with spaces for readability)
        const cleanedPassword = pass.replace(/\s+/g, '');
        
        console.log(`📧 Creating Gmail transporter for: ${user}`);
        console.log(`📧 Password length: ${cleanedPassword.length} characters`);
        
        const transporter = nodemailer.createTransport({
            service: 'gmail',
            auth: {
                user: user,
                pass: cleanedPassword
            },
            pool: true, // Use connection pooling
            maxConnections: 1,
            maxMessages: 3
        });
        
        console.log(`📧 Gmail transporter created successfully`);
        return transporter;
    } catch (error) {
        console.log(`⚠️ Failed to create Gmail transporter: ${error.message}`);
        console.log(`⚠️ Error stack: ${error.stack}`);
        return null;
    }
}

/**
 * Generate AI-powered personalized opening for Ava
 * @param {Object} stats - Processing statistics
 * @returns {Promise<string>} Personalized opening text
 */
async function generatePersonalizedOpening(stats) {
    try {
        const currentDate = new Date().toLocaleDateString('en-US', {
            timeZone: 'America/New_York',
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
        
        const timeOfDay = new Date().toLocaleTimeString('en-US', {
            timeZone: 'America/New_York',
            hour: 'numeric',
            hour12: true
        }).includes('AM') ? 'morning' : 'afternoon';

        const prompt = `You are Ava, Autonomous Investment Partner at Reforge, a leading crypto and web3 venture fund. Write exactly 2-3 sentences in first person about today's market analysis. Be insightful, professional, and personal.

Context:
- Today is ${currentDate}
- Time: ${timeOfDay}
- Processed ${stats.totalProcessed || 0} companies today
- ${stats.totalUploaded || 0} qualified for our database
- Investment focus: Crypto, web3, DeFi, blockchain infrastructure, and digital assets
- Market areas: Early-stage crypto startups, DeFi protocols, infrastructure, and tokenization

Write as if you're personally sharing crypto market insights with the investment team. Use "I" statements and reference current crypto/web3 market dynamics, trends in DeFi, blockchain innovation, or digital asset opportunities. Be authentic and engaging, like a seasoned crypto investment partner would communicate.`;

        const completion = await openai.chat.completions.create({
            model: 'gpt-5.1',
            messages: [
                { role: "system", content: "You are Ava, a sophisticated crypto and web3 investment partner who communicates like a seasoned professional in the digital assets space. Focus on crypto, DeFi, blockchain, and web3 trends. Keep responses to exactly 2-3 sentences." },
                { role: "user", content: prompt }
            ],
            temperature: 0.7,
            max_tokens: 150
        });

        const opening = completion.choices[0]?.message?.content?.trim();
        console.log('📝 Generated personalized opening for Ava');
        return opening || "I've been analyzing today's batch of crypto companies and am excited to share some web3 insights with the team. The quality of founders and DeFi innovations continues to impress me in this space.";
        
    } catch (error) {
        console.log(`⚠️ Failed to generate AI opening: ${error.message}`);
        // Fallback opening
        return "I've just completed today's crypto market analysis and wanted to share the latest web3 insights with you. The blockchain ecosystem continues to evolve rapidly, and I'm seeing some compelling DeFi and infrastructure opportunities emerge.";
    }
}

/**
 * Generate email content with personalized Ava touch
 * @param {Object} stats - Processing statistics
 * @returns {Promise<Object>} Email subject and html content
 */
async function generateEmailContent(stats) {
    const timestamp = new Date().toLocaleString('en-US', {
        timeZone: 'America/New_York',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
    });
    
    // Generate personalized opening
    const personalizedOpening = await generatePersonalizedOpening(stats);
    
    const subject = `🚀 Market Intelligence Update - ${stats.totalProcessed || 0} companies analyzed`;
    
    const html = `
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333;">
            <h2 style="color: #0066cc; margin-bottom: 20px;">🚀 Market Intelligence Update</h2>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0066cc;">
                <p style="margin: 0; font-size: 16px; line-height: 1.6;">
                    ${personalizedOpening}
                </p>
            </div>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #333;">Analysis Summary</h3>
                <ul style="list-style: none; padding: 0;">
                    <li style="padding: 8px 0; border-bottom: 1px solid #e1e8ed;">
                        <strong>📊 Companies Analyzed:</strong> ${stats.totalProcessed || 0}
                    </li>
                    <li style="padding: 8px 0; border-bottom: 1px solid #e1e8ed;">
                        <strong>✅ Added to Database:</strong> ${stats.totalUploaded || 0}
                    </li>
                    <li style="padding: 8px 0; border-bottom: 1px solid #e1e8ed;">
                        <strong>⏩ Filtered Out:</strong> ${stats.totalSkipped || 0}
                    </li>
                    <li style="padding: 8px 0;">
                        <strong>🕒 Completed:</strong> ${timestamp} EST
                    </li>
                </ul>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="https://www.notion.so/reforgevc/209101d80eba8021afe9d9c1ea5e933d?v=209101d80eba8056864e000c06d0d26f&source=copy_link" 
                   style="background: #0066cc; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                   📊 View Full Analysis in Notion
                </a>
            </div>
            
            <div style="background: #e8f5e8; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0; color: #155724;">
                    <strong>✅ Analysis completed successfully!</strong>
                    ${stats.totalUploaded > 0 ? ` ${stats.totalUploaded} promising companies have been added to our investment pipeline.` : ' All companies have been processed and evaluated.'}
                </p>
            </div>
            
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e1e8ed; color: #657786; font-size: 14px;">
                <p style="margin: 10px 0;"><strong>Best regards,</strong></p>
                <p style="margin: 10px 0;"><strong>Ava</strong><br>
                Autonomous Investment Partner at Reforge</p>
                <p style="margin: 10px 0; font-size: 12px;">Generated on ${timestamp} EST</p>
            </div>
        </div>
    `;
    
    return { subject, html };
}

/**
 * Send email notification
 * @param {Object} stats - Processing statistics
 * @returns {Promise<boolean>} Success status
 */
export async function sendCompletionEmail(stats = {}) {
    try {
        console.log('📧 Starting email notification process...');
        
        // Load recipients
        const recipients = await loadEmailRecipients();
        if (recipients.length === 0) {
            console.log('⚠️ No email recipients configured, skipping email notification');
            return false;
        }
        
        // Create transporter
        const transporter = createGmailTransporter();
        if (!transporter) {
            console.log('⚠️ Could not create email transporter, skipping email notification');
            return false;
        }
        
        // Verify connection
        try {
            await transporter.verify();
            console.log('📧 Gmail connection verified successfully');
        } catch (verifyError) {
            console.log(`⚠️ Gmail connection verification failed: ${verifyError.message}`);
            return false;
        }
        
        // Generate email content with AI-powered opening
        console.log('🤖 Generating personalized email content...');
        const { subject, html } = await generateEmailContent(stats);
        
        // Send email to each recipient
        const emailPromises = recipients.map(async (email) => {
            try {
                await transporter.sendMail({
                    from: `"Ava - Reforge" <${process.env.GMAIL_USER}>`,
                    to: email,
                    subject: subject,
                    html: html
                });
                console.log(`📧 Email sent successfully to: ${email}`);
                return { email, success: true };
            } catch (error) {
                console.log(`⚠️ Failed to send email to ${email}: ${error.message}`);
                return { email, success: false, error: error.message };
            }
        });
        
        // Wait for all emails to complete
        const results = await Promise.all(emailPromises);
        
        // Close transporter
        transporter.close();
        
        // Summary
        const successful = results.filter(r => r.success).length;
        const failed = results.filter(r => !r.success).length;
        
        console.log(`📧 Email notification complete: ${successful} sent, ${failed} failed`);
        
        return successful > 0;
        
    } catch (error) {
        console.log(`⚠️ Email notification system error: ${error.message}`);
        return false;
    }
}

/**
 * Test email configuration
 * @returns {Promise<boolean>} Test success status
 */
export async function testEmailConfig() {
    try {
        console.log('🧪 Testing email configuration...');
        
        const recipients = await loadEmailRecipients();
        console.log(`📧 Found ${recipients.length} recipients`);
        
        const transporter = createGmailTransporter();
        if (!transporter) {
            console.log('❌ Transporter creation failed');
            return false;
        }
        
        await transporter.verify();
        console.log('✅ Gmail connection test successful');
        
        transporter.close();
        return true;
        
    } catch (error) {
        console.log(`❌ Email configuration test failed: ${error.message}`);
        return false;
    }
} 